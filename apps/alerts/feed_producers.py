"""
apps/alerts/feed_producers.py

Surface recent saved-search hits as feed tiles — when a user has unread
matches from their alerts, those products get top placement.
"""
from datetime import timedelta
from apps.feed.registry import register, Producer, Tile


def _saved_search_match_tiles(ctx):
    user = ctx.user
    if not (user and getattr(user, 'is_authenticated', False)):
        return []
    try:
        from apps.alerts.models import AlertDelivery, AlertKind
        from apps.products.models import Product
        from django.utils import timezone
    except Exception:
        return []

    # Last 24h of saved-search matches for this user
    cutoff = timezone.now() - timedelta(hours=24)
    deliveries = (
        AlertDelivery.objects.filter(
            user=user, kind=AlertKind.SAVED_SEARCH,
            delivered_at__gte=cutoff,
        )
        .order_by('-delivered_at')[:5]
    )
    product_ids: list[str] = []
    for d in deliveries:
        product_ids.extend(d.product_ids[:5])
    if not product_ids:
        return []

    products = Product.objects.filter(
        pk__in=product_ids, is_active=True, is_archived=False,
    )
    return [
        Tile(
            id=f'product:{p.pk}', kind='product', ref_id=str(p.pk),
            # Highest baseline — alerts represent strongest intent
            score=0.9,
            diversity_key=f'cat:{p.category_id}' if p.category_id else 'product',
            payload={
                'product_id': str(p.pk), 'title': p.title,
                'price': str(p.price),
                'seller_id': p.store.owner_id if p.store_id else None,
                'category_id': p.category_id,
                'badge': 'alert_match',
            },
            reason='matches your saved search',
        )
        for p in products
    ]


register(Producer(name='alerts.saved_search_matches',
                   fn=_saved_search_match_tiles, section='home',
                   cache_tag='feed:user'))
