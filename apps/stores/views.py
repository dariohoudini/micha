from rest_framework import generics, filters, permissions
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Avg
from django.shortcuts import get_object_or_404

from .models import Store, StoreReview
from .serializers import (
    StoreSerializer, StoreReviewSerializer, PublicStoreSerializer,
    MyStoreWriteSerializer,
)
from apps.products.models import Product
from apps.products.serializers import PublicProductSerializer
from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser


class MyStoreListCreateView(generics.ListCreateAPIView):
    """GET  /api/v1/stores/my/  — list authenticated seller's stores.
    POST /api/v1/stores/my/  — create a new store owned by them.

    Why this view exists
    ────────────────────
    Until this lived here, the stores app had NO create endpoint at
    all (only public list/detail + toggle-open). The SellerSetupPage
    UI was therefore PUTting to /seller/profile/ — which writes a
    SellerProfile row (logo / banner / policies), NOT a Store —
    making every "Save" look like it succeeded while no Store row
    was ever inserted. Result: sellers couldn't publish products
    because ProductCreateView couldn't find a Store, and the dashboard
    couldn't show one.

    ``owner`` is forced to ``request.user`` on create so a malicious
    payload cannot assign the new store to a different user. The
    write serializer marks ``owner`` read-only as a second guard.
    """
    permission_classes = [IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_serializer_class(self):
        # Use the richer read serializer for GET (counts + names),
        # the lean write serializer for POST.
        if self.request.method == 'POST':
            return MyStoreWriteSerializer
        return StoreSerializer

    def get_queryset(self):
        return Store.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class MyStoreDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/PUT/DELETE /api/v1/stores/my/<pk>/.

    Owner-scoped — the queryset is filtered to stores belonging to
    ``request.user`` so a seller can't read or mutate another
    seller's store by guessing its id. Returns 404 (not 403) on
    cross-tenant access to avoid leaking ``store_id`` existence.
    """
    serializer_class = MyStoreWriteSerializer
    permission_classes = [IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Store.objects.filter(owner=self.request.user)


# Backwards-compat alias. Older imports / templates may still
# reference ``MyStoreListView`` — keep it pointing at the new
# combined view so we don't break them.
MyStoreListView = MyStoreListCreateView


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


class ToggleStoreOpenView(APIView):
    """POST /api/v1/stores/toggle-open/ — Toggle store open/closed."""
    permission_classes = [IsAuthenticated, IsNotSuspended]

    def post(self, request):
        try:
            store = Store.objects.get(owner=request.user)
        except Store.DoesNotExist:
            return Response({'error': 'Store not found.'}, status=404)
        store.is_open = not store.is_open
        store.save(update_fields=['is_open'])
        status_text = 'aberta' if store.is_open else 'fechada'
        return Response({
            'is_open': store.is_open,
            'detail': f'Loja agora está {status_text}.'
        })
