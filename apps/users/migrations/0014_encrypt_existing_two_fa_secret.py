"""Data migration: encrypt existing plaintext User.two_fa_secret values.

Why this needs a dedicated migration
─────────────────────────────────────
0013 swapped the field type from CharField to EncryptedCharField. The
schema change ALONE doesn't re-encrypt existing rows — Django just
records the model-level change. Rows that already have plaintext
secrets will be READ through EncryptedCharField.from_db_value, which
attempts to decrypt, fails (plaintext isn't valid Fernet ciphertext),
and falls through to returning the raw value (in DEBUG mode) or
RAISES (in production).

Either outcome is wrong:
  - Returning raw value works "by accident" but on next .save() the
    field encrypts AGAIN, producing double-encrypted ciphertext that
    can never be decrypted. Silent corruption.
  - Raising means 2FA-enrolled users can no longer authenticate.

The fix: a one-shot data migration that reads the raw column via the
raw cursor (bypassing the field's decrypt logic), encrypts the
plaintext using the same Fernet helper, and writes the ciphertext
back via raw UPDATE.

Safety properties
──────────────────
  • Idempotent: rows whose value is ALREADY Fernet-encrypted are
    detected (Fernet ciphertext starts with 'gAAAAA' prefix in
    base64) and skipped.
  • Atomic per-row: each UPDATE is a single statement under the
    migration's transaction.
  • Reversible: the reverse migration decrypts back to plaintext.
    Only useful for rollback testing; production should never roll
    this back because the schema change in 0013 stays.
"""
from django.db import migrations


def _encrypt_existing(apps, schema_editor):
    """For every User row with a non-empty plaintext two_fa_secret,
    encrypt it in place using the EncryptedCharField helper.

    Implementation notes:
      • Uses ``apps.get_model`` to get the model AT THIS MIGRATION
        POINT — guards against future model-field changes breaking
        the migration.
      • Reads via raw cursor to bypass the field's auto-decrypt.
      • Writes via raw UPDATE to bypass auto-re-encrypt-on-save (which
        would double-encrypt).
    """
    from apps.payments.models import EncryptedCharField
    field = EncryptedCharField()

    User = apps.get_model('users', 'User')
    table = User._meta.db_table

    with schema_editor.connection.cursor() as cur:
        cur.execute(
            f"SELECT id, two_fa_secret FROM {table} "
            f"WHERE two_fa_secret IS NOT NULL AND two_fa_secret != ''"
        )
        rows = cur.fetchall()

        encrypted_count = 0
        skipped_count = 0
        for user_id, current_value in rows:
            if not current_value:
                continue

            # Fernet ciphertext always starts with 'gAAAAA' (base64 of
            # the 1-byte version prefix 0x80). Skip already-encrypted
            # rows to make the migration idempotent.
            if str(current_value).startswith('gAAAAA'):
                skipped_count += 1
                continue

            try:
                ciphertext = field._encrypt(current_value)
            except Exception:
                # If encryption fails (FIELD_ENCRYPTION_KEY misconfigured),
                # clear the secret rather than leave plaintext. The user
                # will need to re-enrol in 2FA, which is the safer fail
                # state than leaving plaintext in production.
                cur.execute(
                    f"UPDATE {table} SET two_fa_secret = NULL, "
                    f"two_fa_enabled = FALSE WHERE id = %s",
                    [user_id],
                )
                continue

            cur.execute(
                f"UPDATE {table} SET two_fa_secret = %s WHERE id = %s",
                [ciphertext, user_id],
            )
            encrypted_count += 1

    # Log via migration output — visible in the migrate command output.
    print(
        f'  encrypted {encrypted_count} two_fa_secret rows; '
        f'skipped {skipped_count} already-encrypted rows'
    )


def _decrypt_back(apps, schema_editor):
    """Reverse: decrypt ciphertext back to plaintext. ONLY for rollback
    testing. Production should never roll this back."""
    from apps.payments.models import EncryptedCharField
    field = EncryptedCharField()

    User = apps.get_model('users', 'User')
    table = User._meta.db_table

    with schema_editor.connection.cursor() as cur:
        cur.execute(
            f"SELECT id, two_fa_secret FROM {table} "
            f"WHERE two_fa_secret IS NOT NULL AND two_fa_secret != ''"
        )
        for user_id, current_value in cur.fetchall():
            if not str(current_value).startswith('gAAAAA'):
                continue  # already plaintext
            try:
                plaintext = field._decrypt(current_value)
            except Exception:
                continue
            cur.execute(
                f"UPDATE {table} SET two_fa_secret = %s WHERE id = %s",
                [plaintext, user_id],
            )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_alter_user_two_fa_secret'),
    ]

    operations = [
        migrations.RunPython(_encrypt_existing, _decrypt_back),
    ]
