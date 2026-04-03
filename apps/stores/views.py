from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Avg, Q
from .models import Store
from apps.products.models import Product
from .serializers import StoreSerializer
from apps.products.serializers import PublicProductSerializer


# -----------------------------
# Authenticated user: my stores
# -----------------------------
class MyStoreListView(generics.ListAPIView):
    """
    List stores belonging to the authenticated user
    """
    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Store.objects.filter(owner=self.request.user)


# -----------------------------
# Public stores list
# -----------------------------
class PublicStoreListView(generics.ListAPIView):
    """
    Public list of active stores with search and filter
    """
    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "owner__email", "city"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Store.objects.filter(is_active=True)
        # Optional query params
        city = self.request.query_params.get("city")
        min_rating = self.request.query_params.get("min_rating")

        if city:
            queryset = queryset.filter(city__iexact=city)

        if min_rating:
            queryset = queryset.annotate(avg_rating=Avg("products__rating")).filter(avg_rating__gte=min_rating)

        return queryset


# -----------------------------
# Public store detail with nested products
# -----------------------------
class PublicStoreDetailView(generics.RetrieveAPIView):
    """
    Retrieve a single store and its active products
    """
    serializer_class = StoreSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Store.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        store = self.get_object()
        store_data = StoreSerializer(store).data

        # Nested active products
        products = Product.objects.filter(store=store, is_active=True, is_archived=False)
        store_data["products"] = PublicProductSerializer(products, many=True).data

        return Response(store_data)
