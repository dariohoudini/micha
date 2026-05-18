"""Coupon beat tasks."""
from celery import shared_task
from apps.core.task_locks import singleton_task


@shared_task(name='promotions.coupons_cleanup_expired')
@singleton_task('beat:promotions.coupons_cleanup_expired')
def coupons_cleanup_expired():
    from .coupon_service import cleanup_expired
    return cleanup_expired()
