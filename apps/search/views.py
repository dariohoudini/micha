"""
Search Views
FIX: Search input length-limited to 200 chars — prevents slow query attacks
FIX: Uses PostgreSQL full-text search when available
"""
from django.db import models
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
import logging

logger = logging.getLogger("micha")

MAX_SEARCH_LENGTH = 200  # FIX: Limit search query length


def search_products(query, filters=None):
    from apps.products.models import Product
    from django.conf import settings

    # FIX: Sanitise and limit query length
    query = (query or "").strip()[:MAX_SEARCH_LENGTH]

    qs = Product.objects.filter(
        is_active=True, is_archived=False
    ).select_related("store", "category").prefetch_related("images")

    if not query:
        return qs.order_by("-views")

    db_engine = settings.DATABASES["default"]["ENGINE"]

    if "postgresql" in db_engine:
        try:
            from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
            search_vector = SearchVector("title", weight="A") + SearchVector("description", weight="B")
            search_query = SearchQuery(query)
            qs = qs.annotate(rank=SearchRank(search_vector, search_query)).filter(
                rank__gte=0.1
            ).order_by("-rank", "-views")
        except Exception:
            qs = qs.filter(models.Q(title__icontains=query)).order_by("-views")
    else:
        qs = qs.filter(
            models.Q(title__icontains=query) |
            models.Q(brand__icontains=query) |
            models.Q(tags__name__icontains=query)
        ).distinct().order_by("-views")

    if filters:
        if filters.get("category"):
            qs = qs.filter(category__slug=filters["category"])
        if filters.get("min_price"):
            qs = qs.filter(price__gte=filters["min_price"])
        if filters.get("max_price"):
            qs = qs.filter(price__lte=filters["max_price"])
        if filters.get("condition"):
            qs = qs.filter(condition=filters["condition"])
        if filters.get("city"):
            qs = qs.filter(store__city__iexact=filters["city"])
        if filters.get("brand"):
            qs = qs.filter(brand__iexact=filters["brand"])

    return qs


class SearchView(APIView):
    """
    Hyper-personalised search:
    - Keyword matching
    - Category interest boost from user profile
    - Province-aware ranking
    - Excludes recently purchased
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from middleware.pagination import StandardPagination
        from apps.recommendations.views import SlimProductSerializer

        # FIX: Length limit enforced here too
        query = request.query_params.get("q", "").strip()[:MAX_SEARCH_LENGTH]
        filters = {
            "category": request.query_params.get("category"),
            "min_price": request.query_params.get("min_price"),
            "max_price": request.query_params.get("max_price"),
            "condition": request.query_params.get("condition"),
            "city": request.query_params.get("city"),
            "brand": request.query_params.get("brand"),
        }

        import hashlib
        from apps.core.cache_kit import cached_call

        cache_key = "search:" + hashlib.sha256(
            f"{query}{sorted(filters.items())}{request.query_params.get('page','1')}"
            .encode()
        ).hexdigest()

        # Always write the search-history side effect — that's not cached.
        if query and request.user.is_authenticated:
            try:
                from apps.search.models import SearchHistory
                SearchHistory.objects.get_or_create(
                    user=request.user, query=query.lower()[:100],
                )
            except Exception:
                pass

        def _compute():
            qs = search_products(query, filters)
            paginator = StandardPagination()
            page = paginator.paginate_queryset(qs, request)
            data = SlimProductSerializer(
                page, many=True, context={"request": request}
            ).data
            return paginator.get_paginated_response(data).data

        if not query:
            # Empty-query browse — don't cache (varies too much by filters
            # and personalization down the road).
            return Response(_compute())

        # Stampede protection — a viral search ("iPhone 16" right after
        # launch) hammers this endpoint. Single-flight ensures only ONE
        # DB hit per cache-miss window. SWR keeps latency low past TTL.
        # negative_ttl=30 absorbs "no results" hammering on misspellings.
        result = cached_call(
            cache_key, _compute,
            ttl=300, swr_ttl=300,
            negative_ttl=30,
            lock_ttl=15,  # search query can be slow on large catalogs
        )
        return Response(result)


class SearchSuggestionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # FIX: Length limit on autocomplete too
        from apps.core.cache_kit import cached_call
        from apps.products.models import Product

        q = request.query_params.get("q", "").strip()[:50]
        if len(q) < 2:
            return Response({"suggestions": []})

        def _suggestions():
            return list(Product.objects.filter(
                title__icontains=q, is_active=True,
            ).values_list("title", flat=True).distinct()[:8])

        # Autocomplete fires on every keystroke from every concurrent
        # user — extreme stampede surface. Single-flight + short
        # negative TTL absorbs typo-cascades.
        titles = cached_call(
            f"suggestions:{q}", _suggestions,
            ttl=300, swr_ttl=300,
            negative_ttl=30,
        )
        return Response({"suggestions": titles})


class TrendingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.core.cache_kit import cached_call

        def _trending():
            try:
                from apps.search.models import SearchHistory
                from django.db.models import Count
                return list(
                    SearchHistory.objects.values("query")
                    .annotate(count=Count("id"))
                    .order_by("-count")
                    .values_list("query", flat=True)[:10]
                )
            except Exception:
                return []

        # Homepage feature — hot read. 1-hour TTL with SWR keeps the
        # carousel snappy even as the underlying SearchHistory table
        # grows. Single-flight collapses the homepage-spike stampede.
        trending = cached_call(
            "trending_searches", _trending,
            ttl=3600, swr_ttl=3600,
            lock_ttl=15,
        )
        return Response({"trending": trending})


class SearchEventView(APIView):
    """POST /api/v1/search/event/

    Frontend posts user actions on search results back here so the
    relevance-feedback loop can learn what's actually useful.

    Body:
      query: str
      product_id: uuid
      kind: 'impression' | 'click' | 'cart' | 'purchase'
      position: int (optional)

    Returns 202 always — best-effort telemetry, never blocks the user.
    Rate-limited per user/IP via the standard throttle to prevent abuse.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from apps.search.feedback import log_event, SearchEventKind

        query = (request.data.get('query') or '').strip()[:200]
        product_id = request.data.get('product_id')
        kind = (request.data.get('kind') or '').strip()
        position = request.data.get('position')
        try:
            position = int(position) if position is not None else None
            if position is not None and (position < 1 or position > 10000):
                position = None
        except (TypeError, ValueError):
            position = None

        if kind not in {k.value for k in SearchEventKind}:
            return Response({'error': 'bad_kind'}, status=400)
        if not (query and product_id):
            return Response({'error': 'missing_fields'}, status=400)

        # Anon token derived from session/cookie so we can dedupe and
        # aggregate anonymous behaviour without storing PII.
        anon = ''
        try:
            from hashlib import sha256
            sid = request.session.session_key or ''
            if sid:
                anon = sha256(sid.encode()).hexdigest()[:32]
        except Exception:
            pass

        log_event(
            query=query, product_id=product_id, kind=kind,
            position=position, user=request.user, anon_token=anon,
        )
        return Response({'status': 'accepted'}, status=202)


class SearchEventBatchView(APIView):
    """POST /api/v1/search/event/batch/

    Bulk variant — impressions are fired in batches of ~25 per search to
    reduce per-keystroke chatter. Body: ``{"events": [{...}, {...}]}``.
    """
    permission_classes = [permissions.AllowAny]

    MAX_BATCH = 100

    def post(self, request):
        from apps.search.feedback import log_event, SearchEventKind

        events = request.data.get('events') or []
        if not isinstance(events, list):
            return Response({'error': 'events_must_be_list'}, status=400)
        accepted = 0
        for ev in events[:self.MAX_BATCH]:
            try:
                kind = ev.get('kind')
                if kind not in {k.value for k in SearchEventKind}:
                    continue
                log_event(
                    query=(ev.get('query') or '')[:200],
                    product_id=ev.get('product_id'),
                    kind=kind,
                    position=ev.get('position'),
                    user=request.user,
                )
                accepted += 1
            except Exception:
                pass
        return Response({'accepted': accepted}, status=202)
