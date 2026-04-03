from rest_framework import generics, filters
from rest_framework.permissions import AllowAny
from django.db.models import Q
from .models import Product
from .serializers import PublicProductSerializer

# -----------------------------
# Public product list with filters
# -----------------------------
class PublicProductListView(generics.ListAPIView):
    """
    Public product listing with search & filter
    """
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "store__name"]
    ordering_fields = ["title", "price", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True, is_archived=False).select_related("store", "category")

        # Query params
        category = self.request.query_params.get("category")
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        city = self.request.query_params.get("city")
        search = self.request.query_params.get("search")
        sale_type = self.request.query_params.get("sale_type")  # optional filter

        if category:
            queryset = queryset.filter(category__name__iexact=category)

        if min_price:
            queryset = queryset.filter(price__gte=min_price)

        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        if city:
            queryset = queryset.filter(store__city__iexact=city)

        if sale_type:
            queryset = queryset.filter(sale_type__iexact=sale_type)

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(store__name__icontains=search)
            )

        return queryset.order_by("-created_at")


# -----------------------------
# Public product detail view
# -----------------------------
class PublicProductDetailView(generics.RetrieveAPIView):
    """
    Retrieve a single product by ID
    """
    queryset = Product.objects.filter(is_active=True, is_archived=False)
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # Optional: increment views counter if you add a field
        if hasattr(instance, "views"):
            instance.views = (instance.views or 0) + 1
            instance.save(update_fields=["views"])

        return super().retrieve(request, *args, **kwargs)
