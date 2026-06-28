"""
Marketing engine REST surface — the buyer-facing + seller-facing +
admin endpoints. Heavy use of the services layer so views stay
thin and the same logic can be reused by Celery tasks.
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AdCampaign, AdGroup, BundleDeal, CreatorAccount, CreatorCampaign,
    EmailMarketingCampaign, FlashSaleApplication, FlashSaleItem,
    FlashSaleReservation, FreeGiftPromotion, MarketingEvent,
    MarketingKpiSnapshot, MarketingSegment, MePromotion, PixelEvent,
    PromoGame, PromoGameSpin, PromotionAbuseSignal, PromotionLift,
    PromotionUsage, PushMarketingCampaign, SegmentMembership,
    SmsCampaign, SmsOptIn, SuperDealsCampaign, VolumeDiscount,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH1/2/3 — Promotions list + resolve ───────────────────────

class ActivePromotionsView(generics.ListAPIView):
    """GET /promotions/active/ — public list of currently active
    promotions (excluding code-only ones)."""
    permission_classes = [AllowAny]

    def get(self, request):
        now = timezone.now()
        qs = MePromotion.objects.filter(
            status='active', valid_from__lte=now, valid_until__gte=now,
        ).exclude(distribution_method='code_only').values(
            'id', 'type', 'name', 'description', 'discount_type',
            'discount_value', 'min_order_value', 'valid_until',
            'coupon_code',
        )[:100]
        return Response(list(qs))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resolve_cart_promotions(request):
    """POST /promotions/resolve/  body:
    {subtotal, applied_codes, country, candidate_ids?}."""
    subtotal = Decimal(str(request.data.get('subtotal', 0)))
    applied_codes = request.data.get('applied_codes') or []
    country = (request.data.get('country') or '').upper()
    # Gather candidates: explicit IDs, codes, or active platform-wide.
    candidate_ids = request.data.get('candidate_ids') or []
    qs = MePromotion.objects.filter(status='active')
    if candidate_ids:
        qs = qs.filter(id__in=candidate_ids)
    qs = list(qs[:200])
    if applied_codes:
        extra = MePromotion.objects.filter(
            coupon_code__in=applied_codes, status='active',
        )
        for p in extra:
            if p not in qs:
                qs.append(p)
    result = services.resolve_applicable_promotions(
        candidates=qs, subtotal=subtotal,
        user=request.user, applied_codes=applied_codes, country=country,
    )
    return Response(result)


# ─── CH9 — Coupon collect + redeem ─────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def coupon_collect(request):
    """POST /coupons/collect/  body: {promotion_id} or {coupon_code}."""
    promo = None
    if request.data.get('promotion_id'):
        promo = MePromotion.objects.filter(pk=request.data['promotion_id']).first()
    elif request.data.get('coupon_code'):
        promo = MePromotion.objects.filter(
            coupon_code=request.data['coupon_code'],
        ).first()
    if not promo:
        return Response({'detail': 'not found'}, status=404)
    try:
        result = services.collect_coupon(user=request.user, promotion=promo)
        return Response(result, status=201)
    except services.CouponError as e:
        return Response({'code': e.code, **e.detail}, status=409)


@api_view(['POST'])
@permission_classes([IsAdmin])
def coupon_redeem(request):
    """POST /coupons/redeem/  body: {promotion_id, user_id, order_id,
    discount_amount}. Admin/internal — called by checkout service."""
    promo = get_object_or_404(MePromotion, pk=request.data.get('promotion_id'))
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    try:
        usage = services.redeem_coupon_atomically(
            user=user, promotion=promo,
            order_id=request.data.get('order_id', ''),
            discount_amount=Decimal(str(request.data.get('discount_amount', 0))),
        )
        return Response({'usage_id': usage.pk, 'redeemed': True})
    except services.CouponError as e:
        return Response({'code': e.code, **e.detail}, status=409)


# ─── CH4 — Flash sale applications (seller) ───────────────────

class FlashSaleApplicationView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FlashSaleApplication.objects.filter(seller=self.request.user)

    def list(self, request):
        rows = self.get_queryset().values(
            'id', 'event_slug', 'status', 'auto_validation_passed',
            'submitted_at', 'created_at',
        )
        return Response(list(rows))

    def create(self, request):
        app = FlashSaleApplication.objects.create(
            seller=request.user,
            event_slug=request.data.get('event_slug', '')[:64],
            products=request.data.get('products') or [],
            delivery_guarantee=request.data.get('delivery_guarantee', 'standard'),
            seller_notes=request.data.get('seller_notes', ''),
        )
        result = services.validate_flash_application(app)
        if result['ok']:
            app.status = 'submitted'
            app.submitted_at = timezone.now()
            app.save(update_fields=['status', 'submitted_at'])
        return Response({
            'application_id': str(app.id), 'status': app.status,
            'validation': result,
        }, status=201)


# ─── CH5 — Flash sale stock (buyer-facing) ────────────────────

class FlashSaleStockView(APIView):
    """GET /flash-sales/<event_slug>/stock?products=p1,p2 — used by the
    real-time progress bar polling client."""
    permission_classes = [AllowAny]

    def get(self, request, event_slug):
        products = (request.query_params.get('products') or '').split(',')
        products = [p for p in products if p]
        qs = FlashSaleItem.objects.filter(event_slug=event_slug)
        if products:
            qs = qs.filter(product_id__in=products)
        out = []
        for item in qs:
            out.append({
                'product_id': item.product_id, 'sku_id': item.sku_id,
                'allocated_qty': item.allocated_qty,
                'sold_qty': item.sold_qty,
                'available_qty': item.available_qty,
                'claimed_pct': round(item.claimed_pct, 2),
            })
        return Response(out)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reserve_flash_stock(request):
    item = get_object_or_404(FlashSaleItem, pk=request.data.get('item_id'))
    qty = int(request.data.get('quantity', 1))
    try:
        res = services.reserve_flash_stock(
            item=item, user=request.user, quantity=qty,
            checkout_session_id=request.data.get('checkout_session_id', ''),
        )
    except services.FlashSaleStockError as e:
        return Response({'code': str(e)}, status=409)
    return Response({'reservation_id': str(res.id),
                     'expires_at': res.expires_at.isoformat()},
                    status=201)


# ─── CH6 — Bundle deals (seller CRUD + checkout detection) ────

class SellerBundleView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BundleDeal.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj = BundleDeal.objects.create(
            seller=request.user,
            name=request.data.get('name', '')[:200],
            bundle_type=request.data.get('bundle_type', 'fixed_bundle'),
            components=request.data.get('components') or [],
            bundle_price=request.data.get('bundle_price'),
            discount_type=request.data.get('discount_type', 'fixed_price'),
            discount_value=Decimal(str(request.data.get('discount_value', 0))),
            stock_limit=request.data.get('stock_limit'),
            valid_from=request.data.get('valid_from') or timezone.now(),
            valid_until=request.data.get('valid_until') or (timezone.now()),
            status='active',
        )
        return Response({'bundle_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def detect_bundles_for_cart(request):
    """POST /bundles/detect/  body: {seller_id, cart_items: [{product_id, quantity}]}."""
    seller_id = request.data.get('seller_id')
    cart_items = request.data.get('cart_items') or []
    result = services.detect_applicable_bundles(
        seller_id=seller_id, cart_items=cart_items,
    )
    return Response({'applicable': result})


# ─── CH7 — Volume discounts ───────────────────────────────────

class SellerVolumeDiscountView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VolumeDiscount.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj = VolumeDiscount.objects.create(
            seller=request.user,
            product_id=request.data.get('product_id', '')[:64],
            tiers=request.data.get('tiers') or [],
            valid_from=request.data.get('valid_from') or timezone.now(),
            valid_until=request.data.get('valid_until') or timezone.now(),
        )
        return Response({'id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def compute_volume_discount(request):
    """POST /volume-discounts/compute/  body: {product_id, quantity,
    unit_price}. Public so PDP can preview."""
    result = services.apply_volume_discount(
        product_id=request.data.get('product_id', ''),
        quantity=int(request.data.get('quantity', 1)),
        unit_price=Decimal(str(request.data.get('unit_price', 0))),
    )
    return Response(result or {'discount': None})


# ─── CH8 — Free gifts ─────────────────────────────────────────

class SellerFreeGiftView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FreeGiftPromotion.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj = FreeGiftPromotion.objects.create(
            seller=request.user,
            qualifying_product_id=request.data.get('qualifying_product_id', '')[:64],
            qualifying_min_qty=int(request.data.get('qualifying_min_qty', 1)),
            gift_product_id=request.data.get('gift_product_id', '')[:64],
            gift_sku_id=request.data.get('gift_sku_id', '')[:64],
            gift_quantity=int(request.data.get('gift_quantity', 1)),
            gift_stock_allocated=int(request.data.get('gift_stock_allocated', 0)),
            gift_stock_remaining=int(request.data.get('gift_stock_allocated', 0)),
            valid_from=request.data.get('valid_from') or timezone.now(),
            valid_until=request.data.get('valid_until') or timezone.now(),
        )
        return Response({'id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def detect_free_gifts(request):
    result = services.detect_free_gifts(
        seller_id=request.data.get('seller_id'),
        cart_items=request.data.get('cart_items') or [],
    )
    return Response({'gifts': result})


# ─── CH10 — Spin / scratch ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def play_game(request, game_id):
    game = get_object_or_404(PromoGame, pk=game_id)
    is_extra = bool(request.data.get('is_extra_spin', False))
    try:
        result = services.play_promo_game(
            user=request.user, game=game, is_extra_spin=is_extra,
        )
        return Response(result)
    except services.GameError as e:
        return Response({'code': str(e)}, status=409)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def share_scratch(request, game_id):
    game = get_object_or_404(PromoGame, pk=game_id)
    share = services.record_scratch_share(sharer=request.user, game=game)
    return Response({'share_token': share.share_token}, status=201)


# ─── CH14 — Ad auction (internal) ─────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def ad_auction(request):
    user = request.user if request.user.is_authenticated else None
    winners = services.run_ad_auction(
        search_query=request.data.get('search_query', ''),
        product_id=request.data.get('product_id', ''),
        placement=request.data.get('placement', 'search_results'),
        user=user,
        slots=int(request.data.get('slots', 3)),
    )
    return Response({'winners': winners})


@api_view(['POST'])
@permission_classes([AllowAny])
def ad_click(request):
    user = request.user if request.user.is_authenticated else None
    result = services.record_ad_click(
        impression_id=int(request.data.get('impression_id', 0)),
        user=user,
    )
    if not result:
        return Response({'detail': 'not found'}, status=404)
    return Response(result)


class SellerAdCampaignView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AdCampaign.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'name', 'objective', 'status', 'daily_budget',
            'daily_spend', 'total_spend', 'pacing_multiplier',
            'starts_at', 'created_at',
        )))

    def create(self, request):
        obj = AdCampaign.objects.create(
            seller=request.user,
            name=request.data.get('name', '')[:160],
            objective=request.data.get('objective', 'sales'),
            bid_strategy=request.data.get('bid_strategy', 'manual_cpc'),
            daily_budget=Decimal(str(request.data.get('daily_budget', 0))),
            total_budget=request.data.get('total_budget'),
            currency=request.data.get('currency', 'AOA'),
            starts_at=request.data.get('starts_at') or timezone.now(),
            status='live',
        )
        return Response({'campaign_id': str(obj.id)}, status=201)


# ─── CH16 — Pixel events ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pixel_emit(request):
    """POST /pixel/<provider>/emit/  body: {event_name, payload,
    external_event_id?}."""
    obj = services.emit_pixel_event(
        provider=request.data.get('provider', 'meta'),
        event_name=request.data.get('event_name', ''),
        user=request.user, payload=request.data.get('payload') or {},
        external_event_id=request.data.get('external_event_id', ''),
        hashed_user_data=request.data.get('hashed_user_data') or {},
    )
    return Response({'pixel_event_id': obj.pk,
                     'external_event_id': obj.event_id_external},
                    status=201)


# ─── CH17 — Segments + email campaigns ────────────────────────

class SegmentView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return MarketingSegment.objects.all()

    def list(self, request):
        return Response(list(MarketingSegment.objects.values(
            'id', 'slug', 'name', 'definition', 'estimated_size',
            'last_materialised_at',
        )))

    def create(self, request):
        obj = MarketingSegment.objects.create(
            slug=request.data.get('slug', '')[:50],
            name=request.data.get('name', '')[:120],
            description=request.data.get('description', ''),
            definition=request.data.get('definition') or {},
        )
        return Response({'segment_id': str(obj.id), 'slug': obj.slug}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def materialise_segment_view(request, slug):
    seg = get_object_or_404(MarketingSegment, slug=slug)
    size = services.materialise_segment(seg)
    return Response({'segment_size': size})


class EmailCampaignView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return EmailMarketingCampaign.objects.all()

    def list(self, request):
        return Response(list(EmailMarketingCampaign.objects.values(
            'id', 'name', 'segment_id', 'template_key',
            'scheduled_at', 'status', 'queued_count', 'sent_count',
            'opened_count', 'clicked_count',
        )))

    def create(self, request):
        seg = get_object_or_404(MarketingSegment, pk=request.data.get('segment_id'))
        obj = EmailMarketingCampaign.objects.create(
            name=request.data.get('name', '')[:160],
            segment=seg,
            template_key=request.data.get('template_key', '')[:64],
            subject_override=request.data.get('subject_override', '')[:255],
            scheduled_at=request.data.get('scheduled_at') or timezone.now(),
            status='scheduled',
        )
        return Response({'campaign_id': str(obj.id)}, status=201)


# ─── CH18 — SMS opt-in ────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sms_optin(request):
    obj = services.sms_opt_in(
        user=request.user,
        phone=request.data.get('phone', '')[:30],
    )
    return Response({'opted_in': obj.opted_in})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sms_optout(request):
    return Response({'opted_out': services.sms_opt_out(user=request.user)})


class SmsCampaignView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return SmsCampaign.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'name', 'segment_id', 'body', 'scheduled_at',
            'status', 'queued_count', 'sent_count', 'suppressed_count',
        )))

    def create(self, request):
        seg = get_object_or_404(MarketingSegment, pk=request.data.get('segment_id'))
        obj = SmsCampaign.objects.create(
            name=request.data.get('name', '')[:160],
            segment=seg,
            body=request.data.get('body', '')[:160],
            deep_link=request.data.get('deep_link', '')[:255],
            scheduled_at=request.data.get('scheduled_at') or timezone.now(),
            status='scheduled',
        )
        return Response({'campaign_id': str(obj.id)}, status=201)


# ─── CH19 — Push campaigns ────────────────────────────────────

class PushCampaignView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return PushMarketingCampaign.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'name', 'segment_id', 'ab_split_pct',
            'scheduled_at', 'status', 'queued_count', 'sent_count',
            'opened_count', 'winner_variant',
        )))

    def create(self, request):
        seg = get_object_or_404(MarketingSegment, pk=request.data.get('segment_id'))
        obj = PushMarketingCampaign.objects.create(
            name=request.data.get('name', '')[:160],
            segment=seg,
            ab_split_pct=int(request.data.get('ab_split_pct', 50)),
            scheduled_at=request.data.get('scheduled_at') or timezone.now(),
            status='scheduled',
        )
        return Response({'campaign_id': str(obj.id)}, status=201)


# ─── CH22 — Lift ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def compute_lift_view(request):
    promo = get_object_or_404(MePromotion, pk=request.data.get('promotion_id'))
    window_start = date_cls.fromisoformat(request.data['window_start'])
    window_end = date_cls.fromisoformat(request.data['window_end'])
    obj = services.compute_promotion_lift(
        promotion=promo, window_start=window_start, window_end=window_end,
    )
    return Response({
        'promotion_id': str(promo.id),
        'incremental_gmv': str(obj.incremental_gmv),
        'incremental_conversions_pct': obj.incremental_conversions_pct,
        'roi': obj.roi,
        'test_size': obj.test_size, 'holdout_size': obj.holdout_size,
    })


# ─── CH24 — KPI dashboard ─────────────────────────────────────

class MarketingKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = MarketingKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_marketing_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'total_promotions_active': snap.total_promotions_active,
            'total_promo_redemptions': snap.total_promo_redemptions,
            'total_discount_given': str(snap.total_discount_given),
            'flash_sale_gmv': str(snap.flash_sale_gmv),
            'spin_plays': snap.spin_plays,
            'scratch_plays': snap.scratch_plays,
            'ad_spend': str(snap.ad_spend),
            'creator_gmv': str(snap.creator_gmv),
            'abuse_signals_detected': snap.abuse_signals_detected,
            'by_promo_type': snap.by_promo_type,
        })

    def post(self, request):
        snap = services.snapshot_marketing_kpis()
        return Response({'date': str(snap.snapshot_date),
                         'total_promotions_active': snap.total_promotions_active,
                         'total_promo_redemptions': snap.total_promo_redemptions})


class AdminAbuseSignalsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = PromotionAbuseSignal.objects.values(
            'id', 'user_id', 'promotion_id', 'kind',
            'severity', 'evidence', 'action_taken', 'detected_at',
        )[:200]
        return Response(list(rows))
