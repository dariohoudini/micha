from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from django.db.models import Q

from ..models import Product
from ..serializers import PublicProductSerializer


class PublicProductListView(ListAPIView):
    """
    Public product listing with filters & search
    """
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Only show active and not archived products
        queryset = Product.objects.filter(
            is_active=True,
            is_archived=False
        ).select_related("store", "category")

        # Query parameters
        category = self.request.query_params.get("category")
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        city = self.request.query_params.get("city")
        search = self.request.query_params.get("search")

        # Filters
        if category:
            queryset = queryset.filter(category__name__iexact=category)

        if min_price:
            queryset = queryset.filter(price__gte=min_price)

        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        if city:
            queryset = queryset.filter(store__city__iexact=city)

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )

        return queryset.order_by("-created_at")


class PublicProductDetailView(RetrieveAPIView):
    """
    Public product detail view
    """
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]
    queryset = Product.objects.filter(
        is_active=True,
        is_archived=False
    ).select_related("store", "category")
