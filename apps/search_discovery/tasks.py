"""
Celery beat jobs for search_discovery.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name='search_discovery.refresh_trending')
def refresh_trending():
    """Every 15 min — recompute trending for recently-active products."""
    from . import services
    n = 0
    try:
        from apps.orders.models import OrderItem
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=1)
        product_ids = (
            OrderItem.objects.filter(created_at__gte=cutoff)
            .values_list('product__id', flat=True).distinct()[:200]
        )
        for pid in product_ids:
            services.compute_trending_score(product_id=str(pid))
            n += 1
    except Exception:
        pass
    return {'computed': n}


@shared_task(name='search_discovery.weekly_digest_all')
def weekly_digest_all():
    """Monday morning — generate digests for active buyers."""
    from django.contrib.auth import get_user_model
    from . import services
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            run = services.generate_email_digest(user=u)
            if run.status == 'generated':
                n += 1
        except Exception:
            pass
    return {'generated': n}


@shared_task(name='search_discovery.rebuild_related_searches')
def rebuild_related_searches_task():
    from . import services
    return {'rows': services.rebuild_related_searches()}


@shared_task(name='search_discovery.rebuild_autocomplete')
def rebuild_autocomplete_task():
    from . import services
    return {'rows': services.rebuild_autocomplete()}


@shared_task(name='search_discovery.badge_integrity')
def badge_integrity_task():
    from . import services
    return {'checked': services.run_badge_integrity_checks()}


@shared_task(name='search_discovery.decay_new_arrivals')
def decay_new_arrivals_task():
    from . import services
    return {'decayed': services.decay_new_arrivals()}


@shared_task(name='search_discovery.snapshot_search_kpis')
def snapshot_search_kpis_task():
    from . import services
    snap = services.snapshot_search_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='search_discovery.seller_ranking_all')
def seller_ranking_all():
    """Daily seller ranking signal snapshot."""
    from django.contrib.auth import get_user_model
    from . import services
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.filter(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.snapshot_seller_ranking(seller=u); n += 1
        except Exception:
            pass
    return {'snapshots': n}
