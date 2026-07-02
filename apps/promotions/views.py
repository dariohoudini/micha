from rest_framework.permissions import AllowAny
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from django.utils import timezone
from .models import Coupon, FlashSale, UserCoupon, StockNotification
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


# ─── User Process Flow §16.2 — collected-coupon wallet ──────────────

class UserCouponSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source='coupon.code', read_only=True)
    discount_type = serializers.CharField(source='coupon.discount_type', read_only=True)
    discount_value = serializers.DecimalField(source='coupon.discount_value', max_digits=10, decimal_places=2, read_only=True)
    valid_until = serializers.DateTimeField(source='coupon.valid_until', read_only=True)
    min_order_amount = serializers.DecimalField(source='coupon.min_order_amount', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = UserCoupon
        fields = ['id', 'code', 'discount_type', 'discount_value',
                  'valid_until', 'min_order_amount', 'status',
                  'collected_at', 'used_at', 'order_id']
        read_only_fields = fields


class MyCouponsView(generics.ListAPIView):
    """GET /api/v1/promotions/coupons/mine/ — buyer's collected coupons."""
    serializer_class = UserCouponSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        qs = UserCoupon.objects.filter(user=self.request.user).select_related('coupon')
        status_param = self.request.query_params.get('status')
        if status_param in ('available', 'used', 'expired'):
            qs = qs.filter(status=status_param)
        return qs


class CollectCouponView(APIView):
    """POST /api/v1/promotions/coupons/collect/ — save a coupon."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        # Accept either the human code (voucher wall input) or coupon_id
        # (offline replay / one-tap collect chips carry only the id).
        code = (request.data.get('code') or '').strip().upper()
        coupon_id = request.data.get('coupon_id')
        try:
            if code:
                coupon = Coupon.objects.get(code=code, is_active=True)
            elif coupon_id:
                coupon = Coupon.objects.get(pk=coupon_id, is_active=True)
            else:
                return Response({'error': 'code required'}, status=400)
        except (Coupon.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'invalid', 'detail': 'Cupão inválido.'}, status=404)
        now = timezone.now()
        if coupon.valid_until and coupon.valid_until < now:
            return Response({'error': 'expired'}, status=400)
        if coupon.valid_from and coupon.valid_from > now:
            return Response({'error': 'not_yet_valid'}, status=400)
        uc, created = UserCoupon.objects.get_or_create(
            user=request.user, coupon=coupon,
            defaults={'status': 'available'},
        )
        # User Process Flow §20.8 telemetry.
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(
                user=request.user, event='coupon.collected',
                properties={'code': code, 'created': created},
            )
        except Exception:
            pass
        return Response(UserCouponSerializer(uc).data, status=201 if created else 200)


# ─── User Process Flow §7.6 — Notify Me when back in stock ──────────

class StockNotificationSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='product.title', read_only=True)
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = StockNotification
        fields = ['id', 'product', 'product_title', 'product_image',
                  'sku_id', 'created_at', 'is_notified', 'notified_at']
        read_only_fields = ['id', 'product_title', 'product_image',
                            'created_at', 'is_notified', 'notified_at']

    def get_product_image(self, obj):
        img = obj.product.images.first() if hasattr(obj.product, 'images') else None
        return getattr(img.image, 'url', None) if img and getattr(img, 'image', None) else None


class StockNotificationListCreateView(generics.ListCreateAPIView):
    """GET / POST /api/v1/promotions/stock-notify/"""
    serializer_class = StockNotificationSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        return StockNotification.objects.filter(user=self.request.user).select_related('product')

    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(
                user=self.request.user, event='stock.notify_requested',
                properties={'product_id': instance.product_id, 'sku_id': instance.sku_id},
            )
        except Exception:
            pass


# ─── AliExpress Complete 2025 CH 17.3 — Major Sale Events ──────────

from .models import SaleEvent


class SaleEventSerializer(serializers.ModelSerializer):
    is_live = serializers.SerializerMethodField()

    class Meta:
        model = SaleEvent
        fields = ['id', 'name', 'slug', 'kind', 'headline', 'subheading',
                  'banner_image', 'bg_color', 'starts_at', 'ends_at',
                  'cta_label', 'cta_url', 'is_live']
        read_only_fields = ['id', 'is_live']

    def get_is_live(self, obj):
        return obj.is_live()


class LiveSaleEventsView(generics.ListAPIView):
    """GET /api/v1/promotions/sale-events/ — public, only live ones."""
    serializer_class = SaleEventSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        now = timezone.now()
        return SaleEvent.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).order_by('-starts_at')


class AdminSaleEventListCreateView(generics.ListCreateAPIView):
    serializer_class = SaleEventSerializer
    permission_classes = [IsAdminOrSuperuser]
    queryset = SaleEvent.objects.all().order_by('-starts_at')
