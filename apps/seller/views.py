from rest_framework import generics, permissions, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, Count, F, FloatField
from django.shortcuts import get_object_or_404
from django.db.models.functions import Coalesce

from .models import SellerVerification
from apps.stores.models import Store
from apps.products.models import Product
from .serializers import SellerVerificationSerializer
from apps.stores.serializers import StoreSerializer
from apps.products.serializers import ProductSerializer
from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser
from rest_framework.permissions import AllowAny


# -------------------------
# Seller Verification
# -------------------------
class SellerVerificationView(generics.RetrieveUpdateAPIView):
    serializer_class = SellerVerificationSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_object(self):
        return SellerVerification.objects.get_or_create(user=self.request.user)[0]


# -------------------------
# Seller Dashboard
# -------------------------
class SellerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get(self, request):
        user = request.user
        stores = Store.objects.filter(owner=user)
        total_stores = stores.count()
        total_products = Product.objects.filter(store__owner=user).count()
        total_quantity = Product.objects.filter(store__owner=user).aggregate(
            total=Coalesce(Sum('quantity'), 0)
        )['total']

        # Compute total revenue (price * quantity sold, assuming quantity represents available stock)
        total_revenue = Product.objects.filter(store__owner=user).aggregate(
            revenue=Coalesce(Sum(F('price') * F('quantity'), output_field=FloatField()), 0)
        )['revenue']

        # Average store rating
        average_rating = stores.aggregate(avg_rating=Coalesce(Sum(F('products__rating')) / Count('products__rating'), 0))['avg_rating']

        # Total reviews across all products
        total_reviews = Product.objects.filter(store__owner=user).aggregate(total=Coalesce(Sum('reviews__count'), 0))['total']

        return Response({
            "message": f"Welcome, {user.email}!",
            "total_stores": total_stores,
            "total_products": total_products,
            "total_quantity": total_quantity,
            "total_revenue": round(total_revenue, 2),
            "average_store_rating": round(average_rating, 2),
            "total_reviews": total_reviews,
        })


# -------------------------
# Store CRUD for Seller
# -------------------------
class StoreCreateView(generics.CreateAPIView):
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]


class StoreUpdateView(generics.RetrieveUpdateAPIView):
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_object(self):
        return get_object_or_404(Store, owner=self.request.user)


class SellerStoreListView(generics.ListAPIView):
    """
    List all stores owned by the authenticated seller
    """
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Store.objects.filter(owner=self.request.user)


# -------------------------
# Product CRUD for Seller
# -------------------------
class ProductCreateView(generics.CreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]


class ProductUpdateView(generics.RetrieveUpdateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_object(self):
        return get_object_or_404(Product, pk=self.kwargs['pk'], store__owner=self.request.user)


class SellerProductListView(generics.ListAPIView):
    """
    List all products of the authenticated seller with optional search/filter
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "category__name"]
    ordering_fields = ["title", "price", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Product.objects.filter(store__owner=self.request.user)
        category = self.request.query_params.get("category")
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")

        if category:
            queryset = queryset.filter(category__name__iexact=category)
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        return queryset
