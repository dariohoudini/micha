"""Logistics automation (doc CH23)."""
from celery import shared_task


@shared_task(name='last_mile.assign_pending_shipments')
def assign_pending_shipments():
    """JOB 1 — assign couriers to ready shipments (every 30 min)."""
    from . import services
    from .models import LastMileShipment
    assigned = 0
    for s in LastMileShipment.objects.filter(
            status='ready', courier__isnull=True)[:200]:
        if services.assign_courier(s):
            assigned += 1
    return {'assigned': assigned}


@shared_task(name='last_mile.optimise_routes')
def optimise_routes():
    """JOB 2 — daily route optimisation per active courier."""
    from . import services
    from .models import Courier
    done = 0
    for c in Courier.objects.filter(status__in=('available', 'on_route'))[:500]:
        if services.optimise_route(c):
            done += 1
    return {'routes': done}


@shared_task(name='last_mile.auto_return_failed')
def auto_return_failed():
    """JOB 5 — initiate return for shipments at max attempts."""
    from . import services
    from .models import LastMileShipment
    n = 0
    for s in LastMileShipment.objects.filter(
            status='failed', failure_count__gte=services.MAX_DELIVERY_ATTEMPTS)[:200]:
        services.initiate_return(s, reason='max_attempts_sweep')
        n += 1
    return {'returned': n}


@shared_task(name='last_mile.recompute_courier_scores')
def recompute_courier_scores():
    """JOB 8 — daily courier performance score recompute."""
    from . import services
    from .models import Courier
    n = 0
    for c in Courier.objects.all()[:1000]:
        services.recompute_courier_score(c)
        n += 1
    return {'couriers': n}


@shared_task(name='last_mile.snapshot_kpis')
def snapshot_kpis():
    from . import services
    snap = services.snapshot_kpis()
    return {'date': str(snap.snapshot_date)}
