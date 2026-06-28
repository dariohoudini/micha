"""
Celery beat jobs for cs_ops.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name='cs_ops.sla_sweeper')
def sla_sweeper():
    """Walk active tickets + record breaches; triggers escalations."""
    from . import services
    from .models import SupportTicket
    qs = SupportTicket.objects.filter(
        status__in=('new', 'open', 'pending_buyer',
                     'pending_seller', 'on_hold'),
        resolved_at__isnull=True,
    )[:1000]
    n = 0
    for t in qs:
        try:
            n += services.check_and_record_sla_breach(t)
        except Exception:
            pass
    return {'breaches_recorded': n}


@shared_task(name='cs_ops.snapshot_ticket_trends')
def snapshot_ticket_trends_task():
    from . import services
    return {'buckets': services.snapshot_ticket_trends(hours_back=1)}


@shared_task(name='cs_ops.snapshot_agent_performance')
def snapshot_agent_performance_task():
    from . import services
    return {'agents': services.snapshot_agent_performance()}


@shared_task(name='cs_ops.snapshot_cs_ops_kpis')
def snapshot_cs_ops_kpis_task():
    from . import services
    snap = services.snapshot_cs_ops_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='cs_ops.expire_csat_surveys')
def expire_csat_surveys():
    """Garbage-collect old CSAT survey rows without responses past
    expiry."""
    from .models import CsatSurvey
    qs = CsatSurvey.objects.filter(
        expires_at__lt=timezone.now(),
        response__isnull=True,
    )
    # We keep them but rely on the expires_at filter at submit time.
    return {'unresponded_count': qs.count()}
