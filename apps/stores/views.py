from rest_framework import generics, filters, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Avg
from django.shortcuts import get_object_or_404

from .models import Store, StoreReview
from .serializers import StoreSerializer, StoreReviewSerializer, PublicStoreSerializer
from apps.products.models import Product
from apps.products.serializers import PublicProductSerializer
from apps.users.permissions import IsNotSuspended


class MyStoreListView(generics.ListAPIView):
    """GET /api/stores/my/ — Authenticated user's own stores."""
    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Store.objects.filter(owner=self.request.user)


class PublicStoreListView(generics.ListAPIView):
    """GET /api/stores/ — Public list of all active stores."""
    serializer_class = PublicStoreSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "city"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Store.objects.filter(is_active=True)
        city = self.request.query_params.get("city")
        min_rating = self.request.query_params.get("min_rating")

        if city:
            queryset = queryset.filter(city__iexact=city)

        if min_rating:
            try:
                min_rating = float(min_rating)
                # Annotate with avg rating from StoreReview (not products.rating)
                queryset = queryset.annotate(
                    avg_rating=Avg("reviews__rating")
                ).filter(avg_rating__gte=min_rating)
            except ValueError:
                pass

        return queryset


class PublicStoreDetailView(generics.RetrieveAPIView):
    """GET /api/stores/<pk>/ — Single store with nested active products."""
    serializer_class = PublicStoreSerializer
    permission_classes = [AllowAny]
    queryset = Store.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        store = self.get_object()
        store_data = PublicStoreSerializer(store).data
        products = Product.objects.filter(
            store=store, is_active=True, is_archived=False
        ).select_related('category').prefetch_related('images')
        store_data["products"] = PublicProductSerializer(products, many=True).data
        return Response(store_data)


class StoreReviewCreateView(generics.CreateAPIView):
    """POST /api/stores/<pk>/review/ — Leave a review on a store."""
    serializer_class = StoreReviewSerializer
    permission_classes = [IsAuthenticated, IsNotSuspended]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['store'] = get_object_or_404(Store, pk=self.kwargs['pk'])
        return ctx


class StoreReviewListView(generics.ListAPIView):
    """GET /api/stores/<pk>/reviews/ — All reviews for a store."""
    serializer_class = StoreReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        store = get_object_or_404(Store, pk=self.kwargs['pk'])
        return StoreReview.objects.filter(store=store)
