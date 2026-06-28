"""Inventory automation (doc CH23 — all 10 jobs idempotent + bounded)."""
from celery import shared_task


@shared_task(name='stock_engine.release_expired_reservations')
def release_expired_reservations():
    """JOB 1 — every 2 min. Return expired reservations to available."""
    from . import services
    return services.release_expired_reservations()


@shared_task(name='stock_engine.oversell_monitor')
def oversell_monitor():
    """JOB (CH21 guardrail 4) — real-time oversell / invariant breach scan."""
    from . import services
    return services.oversell_monitor()


@shared_task(name='stock_engine.event_sum_integrity')
def event_sum_integrity():
    """JOB 8 — nightly integrity sweep: event running-sum vs total."""
    from . import services
    return services.event_sum_integrity()


@shared_task(name='stock_engine.snapshot_kpis')
def snapshot_kpis():
    """CH24 — daily inventory KPI snapshot."""
    from . import services
    snap = services.snapshot_kpis()
    return {'date': str(snap.snapshot_date),
            'oversell': snap.oversell_incidents}


@shared_task(name='stock_engine.reconcile_flash_pools')
def reconcile_flash_pools():
    """JOB 7 — post-event flash pool cleanup."""
    from django.utils import timezone
    from . import services
    from .models import FlashStockPool
    done = 0
    for pool in FlashStockPool.objects.filter(
            is_open=True, ends_at__lt=timezone.now())[:200]:
        services.reconcile_flash_pool(pool.id)
        done += 1
    return {'reconciled': done}
