"""
apps/recommendations/feed_producers.py

Personalized feed producer — pulls from the user's product interaction
history to find "similar to what they've engaged with" candidates.
"""
from apps.feed.registry import register, Producer, Tile


def _similar_to_history_tiles(ctx):
    """Use the user's last 20 interactions; surface products that share a
    category with anything they've engaged with."""
    user = ctx.user
    if not (user and getattr(user, 'is_authenticated', False)):
        return []

    try:
        from apps.recommendations.models import ProductInteraction
        from apps.products.models import Product
    except Exception:
        return []

    # Recent interactions → category set
    cat_ids = set(
        ProductInteraction.objects
        .filter(user=user)
        .order_by('-created_at')[:20]
        .values_list('product__category_id', flat=True)
    )
    cat_ids.discard(None)
    if not cat_ids:
        return []

    qs = (
        Product.objects
        .filter(category_id__in=cat_ids, is_active=True, is_archived=False)
        .exclude(interactions__user=user)
        .distinct()
        .order_by('-views')[:30]
    )
    return [
        Tile(
            id=f'product:{p.pk}', kind='product', ref_id=str(p.pk),
            # Higher than trending — personalised wins
            score=0.7,
            diversity_key=f'cat:{p.category_id}',
            payload={
                'product_id': str(p.pk), 'title': p.title,
                'price': str(p.price),
                'seller_id': p.store.owner_id if p.store_id else None,
                'category_id': p.category_id,
            },
            reason='similar to your activity',
        )
        for p in qs
    ]


register(Producer(name='recommendations.similar_to_history',
                   fn=_similar_to_history_tiles, section='home',
                   cache_tag='feed:trending'))
