from rest_framework import generics, permissions, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import ProductVariant, StockReservation, LowStockAlert
from apps.users.permissions import IsSellerOrSuperuser, IsNotSuspended


class VariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ["id", "product", "name", "value", "price_modifier", "quantity", "sku", "is_active"]


class VariantListCreateView(generics.ListCreateAPIView):
    serializer_class = VariantSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser]

    def get_queryset(self):
        product_id = self.request.query_params.get("product_id")
        qs = ProductVariant.objects.filter(product__store__owner=self.request.user)
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs


class VariantDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = VariantSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser]

    def get_queryset(self):
        return ProductVariant.objects.filter(product__store__owner=self.request.user)


class StockReservationView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        from apps.products.models import Product
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        try:
            reservation = StockReservation.reserve(product, request.user, quantity)
            return Response({"detail": "Reserved.", "expires_at": reservation.expires_at}, status=201)
        except ValueError as e:
            return Response({"error": "insufficient_stock", "detail": str(e)}, status=400)


class LowStockAlertView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser]

    def get_queryset(self):
        return LowStockAlert.objects.filter(seller=self.request.user, is_active=True)

    def get(self, request):
        alerts = self.get_queryset().select_related("product")
        return Response([
            {"id": a.id, "product": a.product.title, "threshold": a.threshold}
            for a in alerts
        ])

    def post(self, request):
        from apps.products.models import Product
        product_id = request.data.get("product_id")
        threshold = int(request.data.get("threshold", 5))
        product = get_object_or_404(Product, pk=product_id, store__owner=request.user)
        alert, created = LowStockAlert.objects.get_or_create(
            product=product, seller=request.user,
            defaults={"threshold": threshold}
        )
        return Response({"detail": "Alert set." if created else "Alert updated."}, status=201 if created else 200)
