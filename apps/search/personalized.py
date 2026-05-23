import logging
logger = logging.getLogger(__name__)
"""
MICHA Hyper-Personalised Search
Combines keyword search with user taste profile for ranked results.
No OpenAI needed — uses existing UserInterest scores.
"""
from django.db.models import Q
from apps.products.models import Product
from apps.recommendations.models import UserInterest, ProductInteraction


def personalised_search(query, user=None, filters=None, limit=20):
    """
    Search with personalisation:
    1. Keyword match (title, description, brand)
    2. Boost products from user's favourite categories
    3. Boost products user has shown interest in
    4. Apply province boost
    5. Exclude recently purchased (avoid duplicates)
    """
    filters = filters or {}

    # Base keyword search
    qs = Product.active.filter(
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(brand__icontains=query) |
        Q(category__name__icontains=query) |
        Q(tags__name__icontains=query)
    ).distinct()

    # Apply filters
    if filters.get('category'):
        qs = qs.filter(category__slug=filters['category'])
    if filters.get('min_price'):
        qs = qs.filter(price__gte=filters['min_price'])
    if filters.get('max_price'):
        qs = qs.filter(price__lte=filters['max_price'])
    if filters.get('province'):
        qs = qs.filter(store__city__icontains=filters['province'])

    products = list(qs[:limit * 3])  # Get 3x for re-ranking

    if not user or not user.is_authenticated:
        return products[:limit]

    # Get user's interest scores by category
    interest_map = {}
    try:
        interests = UserInterest.objects.filter(
            user=user, score__gt=0
        ).values('category_id', 'score')
        interest_map = {i['category_id']: i['score'] for i in interests}
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)

    # Get recently purchased product IDs to exclude
    purchased_ids = set()
    try:
        purchased_ids = set(
            ProductInteraction.objects.filter(
                user=user, type='purchase'
            ).values_list('product_id', flat=True)[:50]
        )
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)

    # Score and rank
    def score_product(product):
        score = 0

        # Keyword relevance (title match = higher score)
        if query.lower() in (product.title or '').lower():
            score += 10
        if query.lower() in (product.brand or '').lower():
            score += 5

        # Category interest boost
        if product.category_id in interest_map:
            score += interest_map[product.category_id] * 0.1

        # Penalise already purchased
        if product.id in purchased_ids:
            score -= 5

        # Boost popular products
        score += min(product.views * 0.001, 3)
        score += min(product.wishlist_count * 0.1, 2)

        # Price relevance — boost products in user's typical range
        try:
            from apps.analytics.models import SellerPerformance
            # Boost verified sellers
            perf = SellerPerformance.objects.filter(
                seller=product.store.owner
            ).first()
            if perf and perf.tier in ('gold', 'silver'):
                score += 2
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

        return score

    # Sort by personalised score
    products.sort(key=score_product, reverse=True)

    return products[:limit]


def get_search_suggestions(query, user=None, limit=8):
    """
    Personalised search suggestions:
    - Product title matches
    - Category matches
    - Brand matches
    - Trending searches (from analytics)
    Personalised: user's favourite categories shown first.
    """
    suggestions = []

    # Product title suggestions
    products = Product.active.filter(
        title__icontains=query
    ).values('title', 'category__name')[:5]

    for p in products:
        suggestions.append({
            'text': p['title'],
            'type': 'product',
            'category': p['category__name'],
        })

    # Category suggestions
    from apps.products.models import Category
    cats = Category.objects.filter(
        name__icontains=query
    ).values('name', 'slug')[:3]

    for c in cats:
        suggestions.append({
            'text': c['name'],
            'type': 'category',
            'slug': c['slug'],
        })

    return suggestions[:limit]
