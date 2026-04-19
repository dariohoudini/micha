from rest_framework import generics, filters, permissions
from rest_framework.permissions import AllowAny
from django.db.models import Q

from .models import Listing
from .serializers import ListingSerializer
from apps.users.permissions import IsNotSuspended


class ListingListView(generics.ListAPIView):
    """GET /api/listings/list/ — Public listing browse, no auth needed."""
    serializer_class = ListingSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'city']
    ordering_fields = ['price', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Listing.objects.filter(is_active=True).select_related('owner').prefetch_related('images')

        city = self.request.query_params.get('city')
        sale_type = self.request.query_params.get('sale_type')
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        search = self.request.query_params.get('search')

        if city:
            qs = qs.filter(city__iexact=city)
        if sale_type:
            qs = qs.filter(sale_type=sale_type)
        if min_price:
            qs = qs.filter(price__gte=min_price)
        if max_price:
            qs = qs.filter(price__lte=max_price)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        return qs


class ListingDetailView(generics.RetrieveAPIView):
    """GET /api/listings/detail/<uuid>/ — Single listing detail."""
    serializer_class = ListingSerializer
    permission_classes = [AllowAny]
    queryset = Listing.objects.filter(is_active=True).prefetch_related('images')


class ListingCreateView(generics.CreateAPIView):
    """POST /api/listings/create/ — Create a new listing."""
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]


class MyListingsView(generics.ListAPIView):
    """GET /api/listings/my/ — All listings by the authenticated user."""
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Listing.objects.filter(owner=self.request.user).prefetch_related('images')


class ListingUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/listings/<uuid>/ — Edit or delete own listing."""
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        return Listing.objects.filter(owner=self.request.user)
