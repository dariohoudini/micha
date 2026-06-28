"""Celery tasks for the admin console."""
from celery import shared_task


@shared_task(name='admin_console.expire_stale_approvals')
def expire_stale_approvals():
    from . import services
    return services.expire_stale_approvals()


@shared_task(name='admin_console.apply_due_fee_changes')
def apply_due_fee_changes():
    from . import services
    return services.apply_due_fee_changes()


@shared_task(name='admin_console.publish_due_banners')
def publish_due_banners():
    from . import services
    return services.publish_due_banners()


@shared_task(name='admin_console.snapshot_admin_kpis')
def snapshot_admin_kpis():
    from . import services
    snap = services.snapshot_admin_kpis()
    return {'date': str(snap.snapshot_date)}
