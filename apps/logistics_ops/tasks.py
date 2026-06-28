"""
Celery beat jobs for logistics_ops.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone


log = logging.getLogger(__name__)


@shared_task(name='logistics_ops.compute_carrier_sla')
def compute_carrier_sla_task():
    """CH18 — daily SLA snapshot for yesterday."""
    from . import services
    n = services.compute_carrier_sla_snapshot()
    return {'rows': n}


@shared_task(name='logistics_ops.snapshot_logistics_kpis')
def snapshot_logistics_kpis_task():
    """CH24 — daily KPI roll-up."""
    from . import services
    snap = services.snapshot_logistics_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='logistics_ops.expire_pickup_holds')
def expire_pickup_holds():
    """CH21 — return parcels at pickup points past their deadline."""
    from .models import PickupPointDelivery
    n = PickupPointDelivery.objects.filter(
        status__in=('in_transit', 'ready'),
        deadline_at__lt=timezone.now(),
    ).update(status='expired')
    return {'expired': n}


@shared_task(name='logistics_ops.expire_duty_estimates')
def expire_duty_estimates():
    """Garbage-collect expired duty estimates so the cache table
    doesn't grow forever."""
    from .models import DutyEstimate
    cutoff = timezone.now() - timedelta(days=30)
    DutyEstimate.objects.filter(expires_at__lt=cutoff).delete()
    return {'ok': True}


@shared_task(name='logistics_ops.poll_carrier_tracking')
def poll_carrier_tracking():
    """Poll carriers that don't push webhooks. Stub for production:
    walk active labels with a status older than 24h and re-query."""
    return {'polled': 0}
