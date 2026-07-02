"""
Backfill the hash chain over journal entries that predate tamper-evidence
(Gap-Coverage CH7 — same treatment the admin audit trail got in
admin_actions/0003_backfill_audit_chain).

Existing JournalEntry rows have no seq/prev_hash/entry_hash. Walk them in
posting order, assign a monotonic seq, and compute the chain so the whole
journal verifies end-to-end from row 1 — otherwise verify_journal_chain
would report a break at the first legacy row. The payload here MUST match
JournalEntry.chain_payload() exactly, since verification recomputes the
hash from those same stored fields.
"""
from django.db import migrations


def _payload(row, lines):
    return {
        'seq': row.seq,
        'entry_date': row.entry_date.isoformat() if row.entry_date else None,
        'period': row.period,
        'description': row.description,
        'source_type': row.source_type,
        'source_id': row.source_id,
        'posted_by_id': row.posted_by_id,
        'is_auto': row.is_auto,
        'is_reversal': row.is_reversal,
        'reversed_entry_id': str(row.reversed_entry_id) if row.reversed_entry_id else None,
        'total_cents': row.total_cents,
        'lines': [[ln.account_id, ln.debit_cents, ln.credit_cents]
                  for ln in lines],
    }


def backfill_chain(apps, schema_editor):
    from apps.core.audit_chain import compute_entry_hash
    JournalEntry = apps.get_model('accounting', 'JournalEntry')
    JournalLine = apps.get_model('accounting', 'JournalLine')
    prev_hash = ''
    seq = 0
    for row in JournalEntry.objects.order_by('posted_at', 'pk').iterator():
        seq += 1
        row.seq = seq
        row.prev_hash = prev_hash
        lines = list(JournalLine.objects.filter(entry=row).order_by('pk'))
        row.entry_hash = compute_entry_hash(_payload(row, lines), prev_hash)
        row.save(update_fields=['seq', 'prev_hash', 'entry_hash'])
        prev_hash = row.entry_hash


def noop(apps, schema_editor):
    # Reverse: leave the chain fields in place; the schema migration's
    # reverse removes the columns.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0003_journalentry_entry_hash_journalentry_prev_hash_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_chain, noop),
    ]
