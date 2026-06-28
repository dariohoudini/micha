"""Celery tasks for seller tools."""
from celery import shared_task


@shared_task(name='seller_tools.auto_resume_holiday_mode')
def auto_resume_holiday_mode():
    from . import services
    return services.auto_resume_due()


@shared_task(name='seller_tools.generate_commission_statements')
def generate_commission_statements():
    """Run on the 3rd of each month for the previous month."""
    from datetime import date
    from django.contrib.auth import get_user_model
    from . import services

    today = date.today()
    year = today.year if today.month > 1 else today.year - 1
    month = today.month - 1 if today.month > 1 else 12
    generated = 0
    User = get_user_model()
    # Sellers with at least one store.
    for seller in User.objects.filter(stores__isnull=False).distinct():
        try:
            services.generate_commission_statement(seller, year, month)
            generated += 1
        except Exception:
            continue
    return {'generated': generated, 'period': f'{year}-{month:02d}'}


@shared_task(name='seller_tools.recompute_listing_quality')
def recompute_listing_quality(limit=500):
    """Nightly LQS refresh for active listings."""
    from apps.products.models import Product
    from . import services
    n = 0
    for p in Product.objects.filter(is_active=True).select_related(
            'store', 'category')[:limit]:
        try:
            services.compute_listing_quality_score(p)
            n += 1
        except Exception:
            continue
    return {'scored': n}


@shared_task(name='seller_tools.snapshot_kpis')
def snapshot_kpis():
    from . import services
    snap = services.snapshot_seller_tools_kpis()
    return {'date': str(snap.snapshot_date)}
