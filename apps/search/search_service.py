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

        # Full-text search across name + description.
        # Sanitise BEFORE tokenising — caps total length, strips control
        # characters, escapes LIKE wildcards (% and _). Untokenised /
        # unsanitised input was a real pathological-input vector: a 5000-
        # char single token compiled to a Postgres LIKE that pinned a
        # worker for seconds.
        if query:
            from .safe_query import sanitize_query, tokenize_safe
            tokens = tokenize_safe(sanitize_query(query))
            if tokens:
                q_filter = Q()
                for tok in tokens:
                    q_filter |= (
                        Q(title__icontains=tok) |
                        Q(description__icontains=tok)
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

        # Sorting — pick fields that EXIST on Product. The legacy
        # sort_map referenced fields (total_views / avg_rating /
        # is_express) that don't live on the current model; building
        # the orderable list from _meta avoids FieldError at query time
        # and keeps the contract resilient as the schema evolves.
        _fields = {f.name for f in Product._meta.get_fields()}

        def _ord(*candidates):
            return [c for c in candidates if c.lstrip('-') in _fields] or ['-created_at']

        sort_map = {
            'relevance':   _ord('-views', '-created_at'),
            'price_asc':   _ord('price'),
            'price_desc':  _ord('-price'),
            'newest':      _ord('-created_at'),
            'rating':      _ord('-views', '-created_at'),
            'popular':     _ord('-views', '-created_at'),
        }
        qs = qs.order_by(*sort_map.get(sort, sort_map['relevance']))

        total = qs.count()
        products = qs[offset:offset + limit]

        # Compute facets for filter UI
        facets = cls._compute_facets(qs)

        # Project to a stable contract — only fields that actually exist
        # on the Product model. Unknown fields raise FieldError at query
        # time which the legacy code masked by never running.
        from apps.products.models import Product as _P
        _all_fields = {f.name for f in _P._meta.get_fields()}
        _projection = [
            f for f in (
                'id', 'title', 'price', 'category',
                'created_at',
            )
            if f in _all_fields
        ]
        return {
            'products': list(products.values(*_projection)),
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
        """Returns autocomplete suggestions for a search prefix.

        Hardening
        ──────────
        • Prefix is sanitised (LIKE-escape, control-strip, length cap)
          before any DB hit. ``%a`` no longer degenerates to "match
          anything starting with anything-then-a".

        • Suggestions FROM users' past search queries
          (SearchQuery.raw_query) are filtered through
          ``trusted_autocomplete_queries`` — only queries searched by
          ≥ N DISTINCT users surface. Without this, a single actor
          could pre-warm the autocomplete stream that every other
          user sees by hammering the same adversarial query for an
          hour.
        """
        if not prefix or len(prefix) < 2:
            return []

        from .safe_query import sanitize_query, trusted_autocomplete_queries
        safe_prefix = sanitize_query(prefix, max_len=40)
        if not safe_prefix:
            return []

        from django.core.cache import cache
        cache_key = f"autocomplete:{safe_prefix.lower()[:20]}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            from apps.products.models import Product
            # Product names are admin/seller-controlled content, OK to
            # serve directly. Still bounded by ``limit``.
            suggestions = list(
                Product.objects.filter(
                    is_active=True,
                    title__istartswith=safe_prefix,
                ).values_list('title', flat=True)
                .distinct()[:limit]
            )

            # Trusted-only suggestions from user search history.
            popular = trusted_autocomplete_queries(safe_prefix, limit=4)
            suggestions = list(dict.fromkeys(suggestions + popular))[:limit]

            cache.set(cache_key, suggestions, timeout=300)  # 5 min cache
            return suggestions
        except Exception:
            return []
