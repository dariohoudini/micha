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

        cache_key = f"search:{query}:{str(sorted(filters.items()))}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        qs = search_products(query, filters)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = SlimProductSerializer(page, many=True, context={"request": request}).data

        if query and request.user.is_authenticated:
            try:
                from apps.search.models import SearchHistory
                SearchHistory.objects.get_or_create(user=request.user, query=query.lower()[:100])
            except Exception:
                pass

        result = paginator.get_paginated_response(data).data
        if query:
            cache.set(cache_key, result, timeout=300)
        return Response(result)


class SearchSuggestionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # FIX: Length limit on autocomplete too
        q = request.query_params.get("q", "").strip()[:50]
        if len(q) < 2:
            return Response({"suggestions": []})
        cache_key = f"suggestions:{q}"
        cached = cache.get(cache_key)
        if cached:
            return Response({"suggestions": cached})
        from apps.products.models import Product
        titles = list(Product.objects.filter(
            title__icontains=q, is_active=True
        ).values_list("title", flat=True).distinct()[:8])
        cache.set(cache_key, titles, timeout=300)
        return Response({"suggestions": titles})


class TrendingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cached = cache.get("trending_searches")
        if cached:
            return Response({"trending": cached})
        try:
            from apps.search.models import SearchHistory
            from django.db.models import Count
            trending = list(SearchHistory.objects.values("query").annotate(
                count=Count("id")
            ).order_by("-count").values_list("query", flat=True)[:10])
        except Exception:
            trending = []
        cache.set("trending_searches", trending, timeout=3600)
        return Response({"trending": trending})
