from rest_framework import generics, permissions, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import ProductVariant, StockReservation, LowStockAlert
from apps.users.permissions import IsSellerOrSuperuser, IsNotSuspended
from apps.idempotency.decorators import idempotent


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
    """POST /api/v1/inventory/reserve/

    Body: ``{product_id?, variant_combo_id?, quantity}`` — exactly one
    of product_id / variant_combo_id is required. Variant-bearing
    products MUST reserve at the combo level; reserving the parent
    product won't actually hold a specific SKU.

    Idempotency REQUIRED. Each call without a key would create a new
    reservation; a buyer that retried over a flaky network would tie
    up 2N units and starve other buyers. The header binds repeats to
    one reservation.

    Routes through ``inventory.service.reserve`` so variant combos +
    per-user cap + atomic decrement are all enforced.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request):
        from apps.products.models import Product
        from apps.inventory.models import ProductVariantCombo
        from apps.inventory.service import (
            reserve as svc_reserve,
            InsufficientStock, ReservationCapReached, InvalidReservationTarget,
            ReservationError,
        )

        product_id = request.data.get("product_id")
        combo_id = request.data.get("variant_combo_id")
        try:
            quantity = int(request.data.get("quantity", 1))
        except (TypeError, ValueError):
            return Response(
                {'error': 'invalid_quantity', 'detail': 'quantity must be an integer'},
                status=400,
            )

        # Forward the Idempotency-Key header into the reservation row
        # so duplicate calls return the existing row even if the outer
        # @idempotent layer doesn't fire (e.g. a different DRF method
        # path or future direct caller).
        idem_key = request.META.get('HTTP_IDEMPOTENCY_KEY', '').strip()[:128]

        product = combo = None
        if combo_id:
            combo = get_object_or_404(
                ProductVariantCombo, pk=combo_id, is_active=True,
            )
        elif product_id:
            product = get_object_or_404(Product, pk=product_id, is_active=True)
        else:
            return Response(
                {'error': 'missing_target',
                 'detail': 'one of product_id or variant_combo_id is required'},
                status=400,
            )

        try:
            reservation = svc_reserve(
                user=request.user,
                product=product, variant_combo=combo,
                quantity=quantity,
                idempotency_key=idem_key,
            )
        except InsufficientStock as e:
            return Response({'error': 'insufficient_stock', 'detail': str(e)}, status=400)
        except ReservationCapReached as e:
            return Response({'error': 'reservation_cap_reached', 'detail': str(e)}, status=429)
        except InvalidReservationTarget as e:
            return Response({'error': 'invalid_target', 'detail': str(e)}, status=400)
        except ReservationError as e:
            return Response({'error': 'reservation_error', 'detail': str(e)}, status=400)

        return Response(
            {
                'detail': 'Reserved.',
                'reservation_id': reservation.id,
                'expires_at': reservation.expires_at,
                'quantity': reservation.quantity,
            },
            status=201,
        )


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
