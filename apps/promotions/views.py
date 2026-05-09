from rest_framework.permissions import AllowAny
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from django.utils import timezone
from .models import Coupon, FlashSale
from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser, IsAdminOrSuperuser


class CouponSerializer(serializers.ModelSerializer):
    is_valid_now = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'discount_type', 'discount_value',
            'min_order_amount', 'max_discount_amount',
            'usage_limit', 'usage_limit_per_user', 'used_count',
            'is_active', 'valid_from', 'valid_until',
            'is_valid_now', 'created_at',
        ]
        read_only_fields = ['id', 'used_count', 'created_at']

    def get_is_valid_now(self, obj):
        return obj.is_valid()


class FlashSaleSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_title = serializers.ReadOnlyField(source='product.title')
    product_slug = serializers.ReadOnlyField(source='product.slug')
    product_thumbnail = serializers.SerializerMethodField()
    discount_percentage = serializers.ReadOnlyField()
    is_live = serializers.ReadOnlyField()

    class Meta:
        model = FlashSale
        fields = [
            'id', 'product', 'product_id', 'product_title', 'product_slug',
            'product_thumbnail',
            'sale_price', 'original_price', 'discount_percentage',
            'start_time', 'end_time', 'is_active', 'is_live', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_product_thumbnail(self, obj):
        try:
            img = obj.product.images.first()
            if img and img.image:
                req = self.context.get('request')
                return req.build_absolute_uri(img.image.url) if req else img.image.url
        except Exception:
            pass
        return None


# ── Coupon Views ──────────────────────────────────────────────

class ValidateCouponView(APIView):
    """POST /api/promotions/coupons/validate/ — { code, subtotal }"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        code = request.data.get('code', '').strip()
        subtotal = float(request.data.get('subtotal', 0))

        try:
            coupon = Coupon.objects.get(code=code, is_active=True)
        except Coupon.DoesNotExist:
            return Response({'error': 'Invalid coupon code.'}, status=400)

        if not coupon.is_valid():
            return Response({'error': 'Coupon is expired or has reached its usage limit.'}, status=400)

        if subtotal < float(coupon.min_order_amount):
            return Response({
                "detail": f"Minimum order amount is {coupon.min_order_amount}."
            }, status=400)

        discount = coupon.calculate_discount(subtotal)
        seller_name = ''
        if coupon.seller_id:
            try:
                seller_name = (
                    getattr(coupon.seller, 'profile', None) and coupon.seller.profile.full_name
                ) or coupon.seller.email.split('@')[0]
            except Exception:
                seller_name = 'Loja'

        return Response({
            "code": coupon.code,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "discount_amount": discount,
            "new_total": round(subtotal - discount, 2),
            "scope": "seller" if coupon.seller_id else "platform",
            "seller_id": coupon.seller_id,
            "seller_name": seller_name,
            "min_order_amount": coupon.min_order_amount,
        })


class AdminCouponListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/promotions/coupons/ — Admin manages coupons."""
    serializer_class = CouponSerializer
    permission_classes = [IsAdminOrSuperuser]
    queryset = Coupon.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SellerCouponListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/promotions/seller/coupons/ — Seller manages own coupons."""
    serializer_class = CouponSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Coupon.objects.filter(seller=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, seller=self.request.user)


# ── Flash Sale Views ──────────────────────────────────────────

class LiveFlashSalesView(generics.ListAPIView):
    """GET /api/promotions/flash-sales/ — All currently live flash sales."""
    serializer_class = FlashSaleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        now = timezone.now()
        return FlashSale.objects.filter(
            is_active=True, start_time__lte=now, end_time__gte=now
        ).select_related('product').prefetch_related('product__images').order_by('end_time')


class SellerFlashSaleView(generics.ListCreateAPIView):
    """GET/POST /api/promotions/seller/flash-sales/ — Seller manages flash sales."""
    serializer_class = FlashSaleSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return FlashSale.objects.filter(product__store__owner=self.request.user)

    def perform_create(self, serializer):
        product = serializer.validated_data['product']
        if product.store.owner != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only create flash sales for your own products.")
        serializer.save(original_price=product.price)
