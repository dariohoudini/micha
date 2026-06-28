"""Celery tasks for mobile app engineering."""
from celery import shared_task


@shared_task(name='mobile_app.dispatch_silent_pushes')
def dispatch_silent_pushes():
    from . import services
    return services.dispatch_silent_pushes()


@shared_task(name='mobile_app.check_crash_spike')
def check_crash_spike():
    from . import services
    return services.check_crash_spike()


@shared_task(name='mobile_app.snapshot_mobile_kpis')
def snapshot_mobile_kpis():
    from . import services
    snapshot = services.snapshot_mobile_kpis()
    return {'date': str(snapshot.snapshot_date), 'dau': snapshot.dau}


@shared_task(name='mobile_app.purge_expired')
def purge_expired():
    from . import services
    return services.purge_expired()
