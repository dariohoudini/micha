"""
apps/two_factor/models.py

Three tables for full 2FA:

  UserTOTP         One row per user with 2FA enabled. Secret is encrypted
                   at rest (uses the project's EncryptedCharField).
                   `enabled_at` is NULL during the setup flow until the
                   user proves they can produce a code — guards against
                   a half-set-up account that locks the user out.

  BackupCode       Disposable one-time codes generated at enrolment.
                   Stored as SHA-256 hashes; the plaintext is shown ONCE
                   at setup. Used to recover when a user loses their
                   authenticator app.

  TrustedDevice    "Remember this device for 30 days" cookies. Hash of the
                   device token + name + last_used_at + expires_at.
                   Skipping the 2FA challenge on a trusted device is
                   bounded by the expiry — no permanent bypass.

A separate 2FAChallenge log lives in ChallengeAttempt for audit + rate-
limit purposes — every code submission writes one row.
"""
import hashlib
import secrets
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

# Encrypted field — already used elsewhere in the codebase
from apps.payments.models import EncryptedCharField


class UserTOTP(models.Model):
    """The 2FA registration for a user. One row per user (OneToOne)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='totp')
    # Base32-encoded TOTP secret. Encrypted at rest.
    secret = EncryptedCharField(max_length=200)
    # NULL during the setup flow; stamped after the user successfully
    # verifies their first code (proves they can actually produce them).
    enabled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    # How many failed challenges since the last success — used to lock
    # the account after N failures (handled in service).
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_enabled(self) -> bool:
        return self.enabled_at is not None

    def __str__(self):
        state = 'enabled' if self.is_enabled else 'pending'
        return f'TOTP({self.user_id}, {state})'


class BackupCode(models.Model):
    """One-time recovery codes. The plaintext is shown to the user at
    setup; we only store the hash so a leaked DB doesn't compromise the
    backup-code mechanism."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='backup_codes')
    # SHA-256 of the plaintext code
    code_hash = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'code_hash'],
                                    name='uniq_user_backup_code'),
        ]
        indexes = [
            models.Index(fields=['user', 'used_at']),
        ]

    @staticmethod
    def hash_code(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_plaintext() -> str:
        """8-character alphanumeric (uppercase) — humans can type these
        when they've lost their phone. Avoid ambiguous chars (0, O, 1, I)."""
        ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(secrets.choice(ALPHABET) for _ in range(8))


class TrustedDevice(models.Model):
    """Long-lived "remember me" token for a specific device. Lets a user
    skip the 2FA challenge for N days on a trusted device. Bounded by
    expires_at — there is no permanent bypass."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    # SHA-256 of the token plaintext. Plaintext is set as a cookie on the
    # user's device; we only keep the hash.
    token_hash = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=80, blank=True,
                            help_text='e.g. "iPhone 14 / Chrome"')
    last_used_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'token_hash'],
                                    name='uniq_user_trusted_token'),
        ]
        indexes = [
            models.Index(fields=['user', 'expires_at']),
        ]

    @staticmethod
    def hash_token(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


class ChallengeOutcome(models.TextChoices):
    SUCCESS         = 'success',         'Success'
    BAD_CODE        = 'bad_code',        'Bad code'
    BACKUP_USED     = 'backup_used',     'Backup code used'
    LOCKED          = 'locked',          'Locked out'
    DEVICE_TRUSTED  = 'device_trusted',  'Trusted device bypass'


class ChallengeAttempt(models.Model):
    """Audit row per 2FA verification attempt. Used by rate-limiting AND
    by security investigations ("when did the attacker stop trying?")."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='challenge_attempts')
    outcome = models.CharField(max_length=16, choices=ChallengeOutcome.choices, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    purpose = models.CharField(max_length=40, blank=True,
                                help_text='e.g. "login", "create_api_key", "issue_payout"')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['outcome', '-created_at']),
        ]
