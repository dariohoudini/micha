"""
apps/disputes/tasks.py

Celery tasks for the dispute lifecycle.

  • sweep_dispute_sla() — runs hourly. Finds disputes where the seller
    has gone silent past auto_resolve_at and applies refund_buyer.
    Disputes where the seller HAS responded but no resolution was
    reached get bumped to under_review (admin queue).

Schedule (add to CELERY_BEAT_SCHEDULE):
    'disputes-sla-sweep': {
        'task': 'disputes.sweep_dispute_sla',
        'schedule': crontab(minute='17'),  # every hour at :17
    }
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone


log = logging.getLogger(__name__)


@shared_task(name='disputes.sweep_dispute_sla')
def sweep_dispute_sla():
    """Auto-resolve disputes that have blown past their SLA.

    Returns a dict summary {resolved: N, escalated: N, errors: N}.
    """
    from .models import Dispute
    from .service import auto_resolve_silent_seller

    now = timezone.now()
    # Query is index-friendly: (status, auto_resolve_at) index exists.
    overdue = list(
        Dispute.objects.filter(status='open', auto_resolve_at__lte=now)
        .order_by('auto_resolve_at')[:200]
    )

    summary = {'resolved': 0, 'escalated': 0, 'errors': 0}
    for d in overdue:
        try:
            before = d.status
            d = auto_resolve_silent_seller(d)
            if d.status == 'resolved':
                summary['resolved'] += 1
            elif d.status == 'under_review':
                summary['escalated'] += 1
            else:
                # Still open — likely because auto_resolve_at was bumped
                # out concurrently. Not an error; just no-op.
                pass
        except Exception:
            summary['errors'] += 1
            log.exception('sweep_dispute_sla: dispute %s failed', d.id)

    log.info('sweep_dispute_sla complete', extra=summary)
    return summary
