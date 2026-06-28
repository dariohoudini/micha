"""
apps/admin_actions/tasks.py

Audit-trail integrity verification (Audit/Compliance/SLA doc CH8 / CH10).

The audit log is hash-chained (see AdminActionLog), but tamper-evidence is
only useful if someone actually *re-verifies* the chain. This task re-walks
it on a schedule, exposes the result as Prometheus gauges, and logs CRITICAL
on a break — because a broken audit chain means the evidence has been altered,
which is a security incident (Monitoring CH23), not a routine warning.
"""
import logging

from celery import shared_task

from apps.core.task_locks import singleton_task

log = logging.getLogger('audit')


@shared_task(name='audit.verify_admin_chain')
@singleton_task('beat:audit.verify_admin_chain')
def verify_admin_action_chain():
    """Re-verify the AdminActionLog hash chain end-to-end and publish health.

    Returns the verify_chain result dict. On a detected break the log line is
    CRITICAL with ``broken_at`` + ``reason`` so the alert pipeline pages
    on-call and the investigation can start at the exact sequence number.
    """
    from .models import AdminActionLog
    from apps.core.audit_chain import verify_chain

    rows = (
        AdminActionLog.objects
        .filter(seq__isnull=False)
        .order_by('seq')
        .iterator()
    )
    result = verify_chain(rows)

    try:
        from apps.telemetry.metrics import audit_chain_intact, audit_chain_length
        audit_chain_intact.labels(log='admin_action').set(1 if result['ok'] else 0)
        audit_chain_length.labels(log='admin_action').set(result['count'])
    except Exception:
        log.debug('audit chain gauge publish failed', exc_info=True)

    if result['ok']:
        log.info('audit.chain_ok', extra={'log': 'admin_action',
                                          'count': result['count']})
    else:
        log.critical('audit.chain_broken', extra={'log': 'admin_action', **result})

    return result
