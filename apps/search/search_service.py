"""
apps/search/search_service.py

Unified search service for MICHA Express.
Currently uses Django ORM — swaps to Elasticsearch with one setting change.

To upgrade to Elasticsearch later:
1. pip install elasticsearch-dsl
2. Set USE_ELASTICSEARCH=True in settings.py
3. Run: python manage.py search_index --rebuild
Everything else stays the same.
"""
from django.conf import settings
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

USE_ELASTICSEARCH = getattr(settings, 'USE_ELASTICSEARCH', False)


class ProductSearchService:
    """
    Searches products with filters, sorting, and relevance ranking.
    Supports NLP-parsed query from SmartSearchService.
    """

    @classmethod
    def search(cls, query: str, filters: dict = None, sort: str = 'relevance',
               limit: int = 20, offset: int = 0, user=None) -> dict:
        """
        Main search entry point.
        Returns {products, total, facets, zero_results, suggestions}
        """
        if USE_ELASTICSEARCH:
            return cls._search_elasticsearch(query, filters, sort, limit, offset, user)
        return cls._search_orm(query, filters, sort, limit, offset, user)

    @classmethod
    def _search_orm(cls, query: str, filters: dict = None,
                    sort: str = 'relevance', limit: int = 20,
                    offset: int = 0, user=None) -> dict:
        """Django ORM search — works without Elasticsearch."""
        try:
            from apps.products.models import Product
        except ImportError:
            return cls._empty_result()

        filters = filters or {}
        qs = Product.objects.filter(is_active=True)

        # Full-text search across name, description, tags
        if query and query.strip():
            words = query.strip().split()[:10]
            q_filter = Q()
            for word in words:
                if len(word) > 1:
                    q_filter |= (
                        Q(name__icontains=word) |
                        Q(description__icontains=word)
                    )
            qs = qs.filter(q_filter)

        # Apply filters
        if filters.get('category'):
            qs = qs.filter(category__iexact=filters['category'])
        if filters.get('price_max'):
            qs = qs.filter(price__lte=filters['price_max'])
        if filters.get('price_min'):
            qs = qs.filter(price__gte=filters['price_min'])
        if filters.get('province'):
            qs = qs.filter(seller__province__icontains=filters['province'])
        if filters.get('condition'):
            qs = qs.filter(condition=filters['condition'])
        if filters.get('is_express'):
            qs = qs.filter(is_express=True)

        # Sorting
        sort_map = {
            'relevance':   ['-total_views', '-avg_rating', '-created_at'],
            'price_asc':   ['price'],
            'price_desc':  ['-price'],
            'newest':      ['-created_at'],
            'rating':      ['-avg_rating'],
            'popular':     ['-total_views'],
        }
        qs = qs.order_by(*sort_map.get(sort, sort_map['relevance']))

        total = qs.count()
        products = qs[offset:offset + limit]

        # Compute facets for filter UI
        facets = cls._compute_facets(qs)

        return {
            'products': list(products.values(
                'id', 'name', 'price', 'category',
                'avg_rating', 'total_views', 'is_express',
                'created_at'
            )),
            'total': total,
            'facets': facets,
            'zero_results': total == 0,
            'suggestions': cls._get_suggestions(query) if total == 0 else [],
        }

    @classmethod
    def _compute_facets(cls, qs) -> dict:
        """Computes filter facets from result set."""
        from django.db.models import Count, Min, Max
        try:
            categories = list(
                qs.values('category').annotate(count=Count('id'))
                .order_by('-count')[:10]
            )
            price_range = qs.aggregate(min=Min('price'), max=Max('price'))
            return {
                'categories': categories,
                'price_range': {
                    'min': float(price_range['min'] or 0),
                    'max': float(price_range['max'] or 999999),
                }
            }
        except Exception:
            return {}

    @classmethod
    def _get_suggestions(cls, query: str) -> list:
        """Returns broader search suggestions when query has zero results."""
        suggestions = []
        if query:
            words = query.split()
            if len(words) > 1:
                suggestions.append({
                    'type': 'broader',
                    'label': f'Pesquisar apenas "{words[0]}"',
                    'query': words[0],
                })
        suggestions.append({
            'type': 'browse',
            'label': 'Ver todos os produtos',
            'query': '',
        })
        return suggestions

    @classmethod
    def _search_elasticsearch(cls, query, filters, sort, limit, offset, user):
        """
        Elasticsearch implementation — activated when USE_ELASTICSEARCH=True.
        Upgrade path: pip install elasticsearch-dsl, set USE_ELASTICSEARCH=True.
        """
        try:
            from elasticsearch_dsl import Search
            from elasticsearch_dsl.connections import connections

            connections.create_connection(
                hosts=[getattr(settings, 'ELASTICSEARCH_URL', 'http://localhost:9200')]
            )

            s = Search(index='micha_products')
            if query:
                s = s.query('multi_match', query=query,
                            fields=['name^3', 'description', 'category^2'],
                            fuzziness='AUTO')

            filters = filters or {}
            if filters.get('category'):
                s = s.filter('term', category=filters['category'])
            if filters.get('price_max'):
                s = s.filter('range', price={'lte': filters['price_max']})
            if filters.get('price_min'):
                s = s.filter('range', price={'gte': filters['price_min']})

            total = s.count()
            results = s[offset:offset + limit].execute()

            return {
                'products': [hit.to_dict() for hit in results],
                'total': total,
                'facets': {},
                'zero_results': total == 0,
                'suggestions': [],
            }
        except Exception as e:
            logger.error(f"Elasticsearch search failed, falling back to ORM: {e}")
            return cls._search_orm(query, filters, sort, limit, offset, user)

    @staticmethod
    def _empty_result():
        return {'products': [], 'total': 0, 'facets': {}, 'zero_results': True, 'suggestions': []}


class AutocompleteService:
    """
    Search autocomplete — prefix matching on product names.
    Uses Redis cache for speed.
    """

    @classmethod
    def suggest(cls, prefix: str, limit: int = 8) -> list:
        """Returns autocomplete suggestions for a search prefix."""
        if not prefix or len(prefix) < 2:
            return []

        from django.core.cache import cache
        cache_key = f"autocomplete:{prefix.lower()[:20]}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            from apps.products.models import Product
            suggestions = list(
                Product.objects.filter(
                    is_active=True,
                    name__istartswith=prefix
                ).values_list('name', flat=True)
                .distinct()[:limit]
            )

            # Also get category matches
            from apps.ai_engine.models import SearchQuery
            popular = list(
                SearchQuery.objects.filter(
                    raw_query__istartswith=prefix,
                    results_count__gt=0,
                ).values('raw_query').distinct()[:4]
                .values_list('raw_query', flat=True)
            )
            suggestions = list(dict.fromkeys(suggestions + popular))[:limit]

            cache.set(cache_key, suggestions, timeout=300)  # 5 min cache
            return suggestions
        except Exception:
            return []
