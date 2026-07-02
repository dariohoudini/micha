"""
Celery beat jobs for data_analytics.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name='data_analytics.snapshot_realtime')
def snapshot_realtime():
    from . import services
    snap = services.snapshot_realtime_metrics()
    return {'bucket': snap.bucket_minute.isoformat()}


@shared_task(name='data_analytics.rollup_query_analytics')
def rollup_query_analytics_task():
    from . import services
    return {'rows': services.rollup_query_analytics()}


@shared_task(name='data_analytics.snapshot_fraud_loss')
def snapshot_fraud_loss_task():
    from . import services
    snap = services.snapshot_fraud_loss()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='data_analytics.snapshot_delivery')
def snapshot_delivery_task():
    from . import services
    snap = services.snapshot_delivery_performance()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='data_analytics.run_dq_checks')
def run_dq_checks_task():
    from . import services
    return services.run_dq_checks()


@shared_task(name='data_analytics.refresh_c360_all',
             soft_time_limit=900, time_limit=1080)  # all-user sweep: 15/18 min
def refresh_c360_all():
    from django.contrib.auth import get_user_model
    from . import services
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.refresh_c360(u); n += 1
        except Exception:
            pass
    return {'refreshed': n}


@shared_task(name='data_analytics.predict_churn_all',
             soft_time_limit=900, time_limit=1080)  # all-user sweep: 15/18 min
def predict_churn_all():
    from django.contrib.auth import get_user_model
    from . import services
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.predict_churn(u); n += 1
        except Exception:
            pass
    return {'predicted': n}


@shared_task(name='data_analytics.compute_monthly_cohorts',
             soft_time_limit=900, time_limit=1080)  # 6-month recompute: 15/18 min
def compute_monthly_cohorts():
    """Recompute the last 6 acquisition-month cohorts."""
    from datetime import timedelta
    from . import services
    today = timezone.now().date()
    n = 0
    for i in range(6):
        month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(i):
            month = (month - timedelta(days=1)).replace(day=1)
        try:
            services.compute_cohort(cohort_month=month); n += 1
        except Exception:
            pass
    return {'cohorts': n}


@shared_task(name='data_analytics.snapshot_platform_kpis')
def snapshot_platform_kpis_task():
    from . import services
    snap = services.snapshot_platform_kpis()
    return {'date': str(snap.snapshot_date)}
