from rest_framework.generics import (
    CreateAPIView,
    UpdateAPIView,
    DestroyAPIView,
    ListAPIView,
)
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from ..models import Product
from ..serializers import (
    SellerProductCreateUpdateSerializer,
    SellerProductListSerializer,
)


class SellerMyProductsListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SellerProductListSerializer

    def get_queryset(self):
        return Product.objects.filter(
            store__owner=self.request.user
        ).select_related("store", "category")


class SellerProductCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SellerProductCreateUpdateSerializer

    def perform_create(self, serializer):
        store = get_object_or_404(
            self.request.user.stores  # or Store.objects.get(owner=...)
        )
        serializer.save(store=store)


class SellerProductUpdateView(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SellerProductCreateUpdateSerializer

    def get_queryset(self):
        return Product.objects.filter(store__owner=self.request.user)


class SellerProductDeleteView(DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(store__owner=self.request.user)
