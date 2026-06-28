"""
Backfill the hash chain over rows that predate tamper-evidence (CH8).

Existing AdminActionLog rows have no seq/prev_hash/entry_hash. Walk them in
creation order, assign a monotonic seq, and compute the chain so the whole
table verifies end-to-end from row 1 — otherwise verify_admin_chain would
report a break at the first legacy row. The payload here MUST match
AdminActionLog.chain_payload() exactly, since verification recomputes from
those same stored fields.
"""
from django.db import migrations


def _payload(row):
    return {
        'seq': row.seq,
        'admin_id': row.admin_id,
        'action': row.action,
        'target_type': row.target_type,
        'target_id': row.target_id,
        'target_repr': row.target_repr,
        'note': row.note,
        'ip_address': row.ip_address,
        'user_agent': row.user_agent,
        'metadata': row.metadata,
        'outcome': row.outcome,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }


def backfill_chain(apps, schema_editor):
    from apps.core.audit_chain import compute_entry_hash
    Model = apps.get_model('admin_actions', 'AdminActionLog')
    prev_hash = ''
    seq = 0
    for row in Model.objects.order_by('created_at', 'pk').iterator():
        seq += 1
        row.seq = seq
        row.prev_hash = prev_hash
        row.entry_hash = compute_entry_hash(_payload(row), prev_hash)
        row.save(update_fields=['seq', 'prev_hash', 'entry_hash'])
        prev_hash = row.entry_hash


def clear_chain(apps, schema_editor):
    Model = apps.get_model('admin_actions', 'AdminActionLog')
    Model.objects.update(seq=None, prev_hash='', entry_hash='')


class Migration(migrations.Migration):

    dependencies = [
        ('admin_actions', '0002_adminactionlog_entry_hash_adminactionlog_outcome_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_chain, clear_chain),
    ]
