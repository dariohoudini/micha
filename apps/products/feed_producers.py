"""
apps/products/feed_producers.py

Product-domain feed producers. Auto-discovered by apps/feed/apps.py.
"""
from apps.feed.registry import register, Producer, Tile


def _trending_tiles(ctx):
    """Globally trending products in the last 7 days. Universal — anon and
    auth users both see this."""
    try:
        from apps.products.models import Product
    except Exception:
        return []

    qs = (
        Product.objects
        .filter(is_active=True, is_archived=False)
        .order_by('-views', '-created_at')[:30]
    )
    return [
        Tile(
            id=f'product:{p.pk}', kind='product', ref_id=str(p.pk),
            # Trending tile baseline score
            score=0.5,
            diversity_key=f'cat:{p.category_id}' if getattr(p, 'category_id', None) else 'product',
            payload={
                'product_id': str(p.pk), 'title': p.title,
                'price': str(p.price),
                'seller_id': p.store.owner_id if hasattr(p, 'store') and p.store_id else None,
                'category_id': getattr(p, 'category_id', None),
            },
            reason='trending',
        )
        for p in qs
    ]


def _new_arrivals_tiles(ctx):
    """Last 7 days of new listings, ranked by recency."""
    try:
        from apps.products.models import Product
        from django.utils import timezone
        from datetime import timedelta
    except Exception:
        return []

    cutoff = timezone.now() - timedelta(days=7)
    qs = (
        Product.objects
        .filter(is_active=True, is_archived=False, created_at__gte=cutoff)
        .order_by('-created_at')[:20]
    )
    return [
        Tile(
            id=f'product:{p.pk}', kind='product', ref_id=str(p.pk),
            score=0.4,
            diversity_key=f'cat:{p.category_id}' if getattr(p, 'category_id', None) else 'product',
            payload={
                'product_id': str(p.pk), 'title': p.title,
                'price': str(p.price),
                'seller_id': p.store.owner_id if hasattr(p, 'store') and p.store_id else None,
                'category_id': getattr(p, 'category_id', None),
                'is_new': True,
            },
            reason='new arrival',
        )
        for p in qs
    ]


register(Producer(name='products.trending', fn=_trending_tiles,
                   section='home', cache_tag='feed:trending'))
register(Producer(name='products.new_arrivals', fn=_new_arrivals_tiles,
                   section='home', cache_tag='feed:catalog'))
