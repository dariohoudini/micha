"""
Celery beat jobs for trust_safety.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name='trust_safety.snapshot_ts_kpis')
def snapshot_ts_kpis_task():
    from . import services
    snap = services.snapshot_ts_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='trust_safety.recompute_buyer_trust_all')
def recompute_buyer_trust_all():
    """Nightly buyer trust score recompute."""
    from django.contrib.auth import get_user_model
    from . import services
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.compute_buyer_trust_score(u); n += 1
        except Exception:
            pass
    return {'updated': n}


@shared_task(name='trust_safety.flag_overdue_le_requests')
def flag_overdue_le_requests():
    """Pings ops when LE response deadlines have lapsed without
    handling."""
    from .models import LawEnforcementRequest, TrustSafetyEvent
    qs = LawEnforcementRequest.objects.filter(
        deadline_at__lt=timezone.now(),
        status__in=('received', 'validating', 'responding'),
    )
    for req in qs[:100]:
        TrustSafetyEvent.log(
            kind='le_request.overdue',
            subject_kind='le_request', subject_id=str(req.id),
            payload={'agency': req.agency,
                     'deadline_at': req.deadline_at.isoformat()},
        )
    return {'overdue': qs.count()}


@shared_task(name='trust_safety.csam_report_sweep')
def csam_report_sweep():
    """Picks up detected-but-not-yet-reported CSAM incidents and
    flags them for NCMEC submission. In dev we just emit an event;
    production wires the NCMEC API."""
    from .models import CsamIncident, TrustSafetyEvent
    qs = CsamIncident.objects.filter(status='detected')
    for inc in qs[:50]:
        TrustSafetyEvent.log(
            kind='csam.ncmec_queued',
            subject_kind='incident', subject_id=str(inc.id),
        )
    return {'queued': qs.count()}


@shared_task(name='trust_safety.expire_age_challenges')
def expire_age_challenges():
    """Per spec age gate challenges live 90 days. Production would
    delete the row; for dev we just count."""
    from datetime import timedelta
    from .models import AgeGateChallenge
    cutoff = timezone.now() - timedelta(days=90)
    return {'eligible_for_purge': AgeGateChallenge.objects.filter(
        challenged_at__lt=cutoff,
    ).count()}
