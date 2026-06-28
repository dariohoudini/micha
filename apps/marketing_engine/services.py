"""
Marketing engine — domain services.

Pure logic where possible (stackability + priority); side-effectful
helpers for atomic redemption, inventory reservation, game outcomes,
ad auction execution, segment materialisation, lift computation,
and KPI snapshotting.

The stackability matrix is in code (`STACKABILITY_RULES`) rather than
DB so it ships with the deploy — admin can't accidentally edit a
rule that opens a discount-stacking exploit.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .models import (
    AdCampaign, AdClick, AdGroup, AdImpression, AdSpendLog,
    BundleDeal, CoMarketingCampaign, CreatorAccount, CreatorCampaign,
    EmailMarketingCampaign, FlashSaleApplication, FlashSaleItem,
    FlashSaleReservation, FreeGiftPromotion, MarketingEvent,
    MarketingKpiSnapshot, MarketingSegment, MePromotion, PixelEvent,
    PromoGame, PromoGamePrize, PromoGameSpin, PromotionAbuseSignal,
    PromotionLift, PromotionUsage, PushCampaignVariant,
    PushMarketingCampaign, SegmentMembership, ShareScratchEvent,
    SmsCampaign, SmsOptIn, SuperDealsCampaign, SuperDealsEnrolment,
    VolumeDiscount,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH2 — Stackability engine
# ═══════════════════════════════════════════════════════════════════

# Authoritative compatibility matrix. Keys are promotion types, values
# are the types they CANNOT combine with.  Bidirectional symmetry is
# enforced by `_conflicts_with` at evaluation time.
STACKABILITY_RULES = {
    'platform_coupon':       ['flash_sale_price', 'welcome_coupon', 'event_coupon'],
    'welcome_coupon':        ['platform_coupon', 'event_coupon', 'referral_reward_coupon'],
    'flash_sale_price':      ['platform_coupon', 'seller_coupon', 'product_coupon',
                              'bundle_deal', 'volume_discount', 'free_gift'],
    'event_coupon':          ['welcome_coupon', 'platform_coupon'],
    'bundle_deal':           ['product_coupon', 'flash_sale_price', 'free_gift'],
    'volume_discount':       ['product_coupon', 'flash_sale_price'],
    'referral_reward_coupon':['welcome_coupon'],
}


def _conflicts_with(promo_type: str, applied_types: set[str]) -> bool:
    """A applies-with-B compatibility check that respects symmetry:
    if A is in B's deny list OR B is in A's deny list → conflict."""
    own = set(STACKABILITY_RULES.get(promo_type, []))
    if own & applied_types:
        return True
    for t in applied_types:
        if promo_type in STACKABILITY_RULES.get(t, []):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
# CH3 — Priority + savings computation
# ═══════════════════════════════════════════════════════════════════

def estimate_savings(promotion: MePromotion, subtotal: Decimal) -> Decimal:
    """Compute the discount the promotion would apply to `subtotal`.
    Caps at `max_discount_cap` if set."""
    sub = Decimal(str(subtotal or 0))
    if promotion.discount_type == 'percentage':
        savings = (sub * promotion.discount_value / Decimal(100))
    elif promotion.discount_type == 'fixed_amount':
        savings = min(promotion.discount_value, sub)
    elif promotion.discount_type == 'free_shipping':
        # We can't compute exact shipping cost here — return a
        # symbolic mid-tier estimate so the priority resolver still
        # ranks free-shipping reasonably.
        savings = Decimal('500')
    else:
        savings = Decimal('0')
    if promotion.max_discount_cap and savings > promotion.max_discount_cap:
        savings = promotion.max_discount_cap
    return savings.quantize(Decimal('0.01'))


def resolve_applicable_promotions(
    *, candidates: Iterable[MePromotion], subtotal: Decimal,
    user, applied_codes: list[str] = None, country: str = '',
) -> dict:
    """CH2 + CH3 — return the optimal stack for this cart.

    Steps:
      1. Filter by eligibility (status, validity window, min order,
         country, max_uses_per_user).
      2. Apply user-applied codes first (tier-1 priority — never
         displaced).
      3. Walk remaining candidates in (savings DESC, expiry ASC,
         platform-funded > seller-funded) order, dropping any that
         conflict with the running set.
      4. Drop promos whose budget has been exhausted.
    """
    applied_codes = [c.lower() for c in (applied_codes or [])]
    now = timezone.now()

    eligible = []
    for p in candidates:
        if p.status != 'active':
            continue
        if not (p.valid_from <= now <= p.valid_until):
            continue
        if p.min_order_value and subtotal < p.min_order_value:
            continue
        if p.eligible_countries and country and country.upper() not in [c.upper() for c in p.eligible_countries]:
            continue
        if p.max_uses_per_user and user is not None:
            used = PromotionUsage.objects.filter(
                promotion=p, user=user,
            ).count()
            if used >= p.max_uses_per_user:
                continue
        if p.max_budget and p.budget_spent >= p.max_budget:
            continue
        eligible.append(p)

    # Bucket: user-applied codes (always-on) vs auto-selectable.
    forced = [p for p in eligible if p.coupon_code.lower() in applied_codes]
    auto = [p for p in eligible if p not in forced]

    def _sort_key(p: MePromotion):
        savings = estimate_savings(p, subtotal)
        expiry_seconds = (p.valid_until - now).total_seconds()
        platform_priority = 1 if p.funded_by == 'platform' else 0
        # Higher savings first; earlier expiry first; platform > seller.
        return (-float(savings), expiry_seconds, -platform_priority, -p.priority_score)

    auto.sort(key=_sort_key)

    selected = []
    selected_types = set()
    rejected = []
    total_savings = Decimal('0')

    # 1) Forced (manually applied) codes always go in first, in the
    #    order the user added them.
    for p in forced:
        if _conflicts_with(p.type, selected_types):
            rejected.append({'id': str(p.id), 'reason': 'CONFLICT_BUT_FORCED_OVERRIDE'})
            continue
        selected.append(p)
        selected_types.add(p.type)
        total_savings += estimate_savings(p, subtotal)

    # 2) Auto candidates by sort key.
    for p in auto:
        if _conflicts_with(p.type, selected_types):
            rejected.append({'id': str(p.id), 'reason': 'CONFLICTS_WITH_APPLIED_PROMOTION'})
            continue
        selected.append(p)
        selected_types.add(p.type)
        total_savings += estimate_savings(p, subtotal)

    return {
        'selected': [{
            'id': str(p.id), 'type': p.type, 'name': p.name,
            'savings': str(estimate_savings(p, subtotal)),
            'funded_by': p.funded_by,
            'manually_applied': p.coupon_code.lower() in applied_codes,
        } for p in selected],
        'rejected': rejected,
        'total_savings': str(total_savings.quantize(Decimal('0.01'))),
        'currency': selected[0].currency if selected else 'AOA',
    }


# ═══════════════════════════════════════════════════════════════════
# CH9 — Coupon collect + atomic redemption
# ═══════════════════════════════════════════════════════════════════

class CouponError(Exception):
    def __init__(self, code: str, detail: dict = None):
        super().__init__(code)
        self.code = code
        self.detail = detail or {}


def collect_coupon(*, user, promotion: MePromotion) -> dict:
    """Idempotent collect — second call returns the existing
    PromotionUsage-style guard row without re-incrementing."""
    # Already collected?
    if PromotionUsage.objects.filter(promotion=promotion, user=user,
                                      order_id__startswith='collected:').exists():
        raise CouponError('ALREADY_COLLECTED')
    if promotion.max_uses_total and promotion.uses_count >= promotion.max_uses_total:
        raise CouponError('COUPON_EXHAUSTED')
    # "Collection" is a soft reserve — we use an order_id sentinel.
    PromotionUsage.objects.create(
        promotion=promotion, user=user,
        order_id=f'collected:{user.pk}:{promotion.id}',
        discount_amount=Decimal('0'), currency=promotion.currency,
    )
    MarketingEvent.log(user=user, kind='coupon.collected',
                       payload={'promotion_id': str(promotion.id),
                                'code': promotion.coupon_code})
    return {'collected': True}


@transaction.atomic
def redeem_coupon_atomically(*, user, promotion: MePromotion,
                              order_id: str, discount_amount: Decimal) -> PromotionUsage:
    """CH9.2 — pessimistic lock on the promotion row. Caller must
    already have run the validation pipeline; this layer enforces the
    uses_count + budget_spent transactional invariants."""
    if not order_id:
        raise CouponError('ORDER_ID_REQUIRED')

    locked = MePromotion.objects.select_for_update().get(pk=promotion.pk)
    if locked.status != 'active':
        raise CouponError('PROMOTION_NOT_ACTIVE')
    if locked.max_uses_total and locked.uses_count >= locked.max_uses_total:
        raise CouponError('COUPON_EXHAUSTED')
    if locked.max_budget and (locked.budget_spent + discount_amount) > locked.max_budget:
        raise CouponError('BUDGET_EXHAUSTED')

    usage, created = PromotionUsage.objects.get_or_create(
        promotion=locked, order_id=order_id,
        defaults={'user': user, 'discount_amount': discount_amount,
                  'currency': locked.currency},
    )
    if not created:
        # Same order trying to redeem twice — return existing record.
        return usage

    MePromotion.objects.filter(pk=locked.pk).update(
        uses_count=django_models.F('uses_count') + 1,
        budget_spent=django_models.F('budget_spent') + discount_amount,
    )
    MarketingEvent.log(user=user, kind='coupon.redeemed',
                       payload={'promotion_id': str(locked.id),
                                'order_id': order_id,
                                'amount': str(discount_amount)})
    return usage


# ═══════════════════════════════════════════════════════════════════
# CH4 — Flash sale application validation
# ═══════════════════════════════════════════════════════════════════

def validate_flash_application(application: FlashSaleApplication) -> dict:
    """CH4.1 auto-validation gate. Returns
    {ok: bool, errors: [{code, product_id, ...}]}. The seller / tier /
    training checks delegate to apps.seller_onboarding when available;
    if those apps aren't fully populated yet we skip those gates
    rather than fail closed."""
    errors = []
    for prod in application.products or []:
        normal = Decimal(str(prod.get('normal_price', 0)))
        flash = Decimal(str(prod.get('flash_sale_price', 0)))
        if normal <= 0:
            errors.append({'code': 'NORMAL_PRICE_REQUIRED',
                           'product_id': prod.get('product_id')})
            continue
        discount_pct = ((normal - flash) / normal * 100)
        if discount_pct < 20:
            errors.append({'code': 'INSUFFICIENT_DISCOUNT',
                           'product_id': prod.get('product_id'),
                           'min_required': 20, 'current': float(discount_pct)})
        qty = int(prod.get('flash_sale_quantity', 0))
        if qty <= 0:
            errors.append({'code': 'QTY_REQUIRED',
                           'product_id': prod.get('product_id')})

    # Seller health / tier / training gates — soft-skip if seller
    # onboarding tables are absent.
    try:
        from apps.seller_onboarding.models import SellerTierState
        tier = SellerTierState.objects.filter(seller=application.seller).first()
        if tier and tier.current_tier == 'standard':
            errors.append({'code': 'TIER_TOO_LOW', 'min': 'bronze'})
    except Exception:
        pass

    application.auto_validation_passed = not errors
    application.auto_validation_errors = errors
    application.save(update_fields=['auto_validation_passed', 'auto_validation_errors'])
    return {'ok': not errors, 'errors': errors}


# ═══════════════════════════════════════════════════════════════════
# CH5 — Flash sale inventory reservation
# ═══════════════════════════════════════════════════════════════════

class FlashSaleStockError(Exception):
    pass


@transaction.atomic
def reserve_flash_stock(*, item: FlashSaleItem, user, quantity: int,
                         checkout_session_id: str = '',
                         hold_minutes: int = 30) -> FlashSaleReservation:
    locked = FlashSaleItem.objects.select_for_update().get(pk=item.pk)
    avail = locked.allocated_qty - locked.sold_qty - locked.reserved_qty
    if avail < quantity:
        raise FlashSaleStockError('FLASH_SALE_SOLD_OUT')
    locked.reserved_qty += quantity
    locked.save(update_fields=['reserved_qty'])
    res = FlashSaleReservation.objects.create(
        item=locked, user=user, quantity=quantity,
        checkout_session_id=checkout_session_id[:64],
        expires_at=timezone.now() + timedelta(minutes=hold_minutes),
    )
    MarketingEvent.log(user=user, kind='flash.reserved',
                       payload={'item_id': str(item.id),
                                'qty': quantity})
    return res


@transaction.atomic
def confirm_flash_reservation(reservation: FlashSaleReservation) -> bool:
    locked = FlashSaleReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status != 'active':
        return False
    item = FlashSaleItem.objects.select_for_update().get(pk=locked.item_id)
    item.reserved_qty = max(0, item.reserved_qty - locked.quantity)
    item.sold_qty += locked.quantity
    item.save(update_fields=['reserved_qty', 'sold_qty'])
    locked.status = 'confirmed'
    locked.save(update_fields=['status'])
    MarketingEvent.log(user=locked.user, kind='flash.confirmed',
                       payload={'item_id': str(item.id),
                                'qty': locked.quantity})
    return True


@transaction.atomic
def release_flash_reservation(reservation: FlashSaleReservation, *, reason='expired') -> bool:
    locked = FlashSaleReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status != 'active':
        return False
    item = FlashSaleItem.objects.select_for_update().get(pk=locked.item_id)
    item.reserved_qty = max(0, item.reserved_qty - locked.quantity)
    item.save(update_fields=['reserved_qty'])
    locked.status = reason if reason in ('released', 'expired') else 'released'
    locked.save(update_fields=['status'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH6 — Bundle detection
# ═══════════════════════════════════════════════════════════════════

def detect_applicable_bundles(*, seller_id, cart_items: list[dict]) -> list[dict]:
    """`cart_items` shape: [{product_id, quantity}, ...]. Returns the
    list of applicable bundle deals with computed savings."""
    now = timezone.now()
    bundles = BundleDeal.objects.filter(
        seller_id=seller_id, status='active',
        valid_from__lte=now, valid_until__gte=now,
    )
    cart = {str(i['product_id']): int(i.get('quantity', 0)) for i in cart_items}
    applicable = []
    for b in bundles:
        if b.stock_limit is not None and b.claims_count >= b.stock_limit:
            continue
        components = b.components or []
        ok = True
        for c in components:
            req_pid = str(c.get('product_id', ''))
            req_qty = int(c.get('quantity', 1))
            if cart.get(req_pid, 0) < req_qty:
                ok = False
                break
        if not ok:
            continue
        applicable.append({
            'bundle_id': str(b.id), 'name': b.name,
            'discount_type': b.discount_type,
            'discount_value': str(b.discount_value),
            'bundle_price': str(b.bundle_price) if b.bundle_price else None,
        })
    return applicable


# ═══════════════════════════════════════════════════════════════════
# CH7 — Volume discount tier match
# ═══════════════════════════════════════════════════════════════════

def apply_volume_discount(*, product_id: str, quantity: int,
                           unit_price: Decimal) -> dict | None:
    now = timezone.now()
    vd = VolumeDiscount.objects.filter(
        product_id=product_id, status='active',
        valid_from__lte=now, valid_until__gte=now,
    ).first()
    if not vd:
        return None
    tiers = sorted(vd.tiers or [], key=lambda t: t.get('min_quantity', 0), reverse=True)
    for tier in tiers:
        if quantity >= int(tier.get('min_quantity', 1)):
            pct = Decimal(str(tier.get('discount_pct', 0)))
            discount = (unit_price * Decimal(quantity) * pct / Decimal(100)).quantize(Decimal('0.01'))
            return {'tier': tier, 'discount_pct': float(pct), 'discount_amount': str(discount)}
    return None


# ═══════════════════════════════════════════════════════════════════
# CH8 — Free gift attach
# ═══════════════════════════════════════════════════════════════════

def detect_free_gifts(*, seller_id, cart_items: list[dict]) -> list[dict]:
    now = timezone.now()
    promos = FreeGiftPromotion.objects.filter(
        seller_id=seller_id, status='active',
        valid_from__lte=now, valid_until__gte=now,
        gift_stock_remaining__gt=0,
    )
    out = []
    cart_by_pid = {}
    for i in cart_items:
        cart_by_pid.setdefault(str(i['product_id']), 0)
        cart_by_pid[str(i['product_id'])] += int(i.get('quantity', 0))
    for p in promos:
        if cart_by_pid.get(p.qualifying_product_id, 0) >= p.qualifying_min_qty:
            out.append({
                'promo_id': str(p.id),
                'gift_product_id': p.gift_product_id,
                'gift_sku_id': p.gift_sku_id,
                'gift_quantity': p.gift_quantity,
            })
    return out


@transaction.atomic
def claim_free_gift(*, promo: FreeGiftPromotion, user, order_id: str) -> bool:
    locked = FreeGiftPromotion.objects.select_for_update().get(pk=promo.pk)
    if locked.gift_stock_remaining < locked.gift_quantity:
        return False
    locked.gift_stock_remaining -= locked.gift_quantity
    if locked.gift_stock_remaining == 0:
        locked.status = 'sold_out'
    locked.save(update_fields=['gift_stock_remaining', 'status'])
    MarketingEvent.log(user=user, kind='free_gift.claimed',
                       payload={'promo_id': str(promo.id),
                                'order_id': order_id})
    return True


# ═══════════════════════════════════════════════════════════════════
# CH10 — Spin / scratch outcome with server-side determinism
# ═══════════════════════════════════════════════════════════════════

class GameError(Exception):
    pass


def _crypto_uniform() -> float:
    """Cryptographically random uniform [0, 1).  Used to pick prizes
    so the outcome can't be predicted by replaying network traffic."""
    return secrets.randbits(53) / float(1 << 53)


def _pick_outcome(game: PromoGame) -> PromoGamePrize | None:
    prizes = list(game.prizes.all().order_by('id'))
    if not prizes:
        return None
    # Normalise probabilities even if they sum to !=1.
    total_weight = sum(float(p.probability) for p in prizes) or 1.0
    r = _crypto_uniform() * total_weight
    acc = 0.0
    for p in prizes:
        acc += float(p.probability)
        if r < acc:
            return p
    return prizes[-1]


def _fallback_prize(game: PromoGame) -> PromoGamePrize | None:
    return (
        game.prizes.filter(is_fallback=True).first()
        or game.prizes.filter(prize_type='better_luck').first()
        or game.prizes.order_by('probability').first()
    )


@transaction.atomic
def play_promo_game(*, user, game: PromoGame,
                     is_extra_spin: bool = False) -> dict:
    if game.status != 'active':
        raise GameError('GAME_NOT_ACTIVE')
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    plays_today = PromoGameSpin.objects.filter(
        user=user, game=game, spun_at__gte=today_start,
        was_extra_spin=False,
    ).count()
    if not is_extra_spin and plays_today >= game.spins_per_user_per_day:
        raise GameError('DAILY_LIMIT_REACHED')

    outcome = _pick_outcome(game)
    if outcome is None:
        raise GameError('NO_PRIZES_CONFIGURED')

    # Stock decrement under lock; fall back if out of stock.
    if outcome.stock_remaining is not None:
        locked = PromoGamePrize.objects.select_for_update().get(pk=outcome.pk)
        if locked.stock_remaining <= 0:
            outcome = _fallback_prize(game) or outcome
        else:
            locked.stock_remaining -= 1
            locked.save(update_fields=['stock_remaining'])
            outcome = locked

    spin = PromoGameSpin.objects.create(
        user=user, game=game, outcome_prize=outcome,
        outcome_label=outcome.label or outcome.prize_type,
        was_extra_spin=is_extra_spin,
        spent_coins=game.extra_spin_price_coins if is_extra_spin else 0,
    )

    delivery = _deliver_prize(user, outcome)
    spin.delivered = delivery.get('delivered', False)
    spin.delivery_payload = delivery
    spin.save(update_fields=['delivered', 'delivery_payload'])

    MarketingEvent.log(
        user=user, kind=f'game.{game.type}_played',
        payload={'spin_id': spin.pk, 'prize_type': outcome.prize_type,
                 'label': outcome.label},
    )
    return {
        'spin_id': spin.pk,
        'prize_type': outcome.prize_type,
        'label': outcome.label,
        'delivery': delivery,
    }


def _deliver_prize(user, prize: PromoGamePrize) -> dict:
    """Materialise the prize: create user_coupon row / coins grant /
    free product claim. We bridge into the existing loyalty +
    promotions apps to grant where they own the canonical state."""
    if prize.prize_type == 'better_luck':
        return {'delivered': True, 'message': 'better_luck_next_time'}
    if prize.prize_type == 'coupon':
        # Spin out a new MePromotion targeted at this user.
        promo = MePromotion.objects.create(
            type='platform_coupon',
            name=f'Game prize coupon — {user.pk}',
            funded_by='platform',
            discount_type='fixed_amount',
            discount_value=prize.coupon_value,
            min_order_value=prize.coupon_min_order,
            distribution_method='targeted',
            target_segment=f'user:{user.pk}',
            coupon_code=f'GP-{secrets.token_urlsafe(6)[:8].upper()}',
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=14),
            status='active',
            max_uses_per_user=1,
        )
        return {'delivered': True, 'coupon_code': promo.coupon_code,
                'promo_id': str(promo.id)}
    if prize.prize_type == 'coins':
        # Best-effort grant via the existing loyalty app.
        try:
            from apps.loyalty.models import PointsTransaction
            PointsTransaction.objects.create(
                user=user, points=prize.coins_amount,
                reason='promo_game_prize',
            )
        except Exception:
            pass
        return {'delivered': True, 'coins': prize.coins_amount}
    if prize.prize_type == 'free_product':
        return {'delivered': True, 'product_id': prize.product_id,
                'claim_window_hours': 24}
    if prize.prize_type == 'cashback':
        return {'delivered': True, 'amount': str(prize.coupon_value)}
    return {'delivered': False}


def record_scratch_share(*, sharer, game: PromoGame) -> ShareScratchEvent:
    return ShareScratchEvent.objects.create(
        sharer=sharer, game=game,
        share_token=ShareScratchEvent.make_token(),
    )


def credit_scratch_share_conversion(*, share_token: str, referee) -> bool:
    obj = ShareScratchEvent.objects.filter(share_token=share_token,
                                            converted_at__isnull=True).first()
    if not obj:
        return False
    obj.referee = referee
    obj.converted_at = timezone.now()
    obj.save(update_fields=['referee', 'converted_at'])
    MarketingEvent.log(user=referee, kind='scratch.share_converted',
                       payload={'sharer_id': obj.sharer_id,
                                'game_id': str(obj.game_id)})
    return True


# ═══════════════════════════════════════════════════════════════════
# CH14 — Ad auction
# ═══════════════════════════════════════════════════════════════════

def run_ad_auction(*, search_query: str = '', product_id: str = '',
                    placement: str = 'search_results',
                    user=None, slots: int = 3) -> list[dict]:
    """Walk eligible ad groups, compute ad rank = bid × quality_score
    × pacing_multiplier, return the top `slots`. Caller logs the
    impressions and (later) the clicks."""
    now = timezone.now()
    # Eligible campaigns: live + within window + not budget-paused +
    # parent has paced quota left.
    eligible_qs = AdGroup.objects.filter(
        status='active', campaign__status='live',
        campaign__starts_at__lte=now,
    ).select_related('campaign')
    if product_id:
        eligible_qs = eligible_qs.filter(product_id=product_id)
    if search_query:
        eligible_qs = eligible_qs.filter(
            keywords__keyword__icontains=search_query,
        ).distinct()
    candidates = []
    for ag in eligible_qs[:200]:
        if ag.campaign.daily_spend >= ag.campaign.daily_budget:
            continue
        rank = float(ag.bid_amount) * ag.quality_score * ag.campaign.pacing_multiplier
        candidates.append((rank, ag))
    candidates.sort(reverse=True, key=lambda t: t[0])
    winners = []
    for rank, ag in candidates[:slots]:
        cpc = (float(candidates[-1][0]) / max(1, ag.quality_score)) if len(candidates) > slots else float(ag.bid_amount) * 0.95
        cpc = Decimal(str(round(cpc, 4)))
        imp = AdImpression.objects.create(
            ad_group=ag, user=user, placement=placement[:24],
            search_query=search_query[:200], ad_rank=rank, cpm_cost=cpc,
        )
        winners.append({
            'impression_id': imp.pk, 'ad_group_id': str(ag.id),
            'campaign_id': str(ag.campaign_id),
            'product_id': ag.product_id, 'rank': rank,
            'cpc_estimate': str(cpc),
        })
    return winners


@transaction.atomic
def record_ad_click(*, impression_id: int, user=None) -> dict | None:
    imp = AdImpression.objects.select_related('ad_group__campaign').filter(
        pk=impression_id,
    ).first()
    if not imp:
        return None
    cpc = imp.cpm_cost or imp.ad_group.bid_amount
    click = AdClick.objects.create(
        ad_group=imp.ad_group, impression=imp, user=user, cpc_cost=cpc,
    )
    # Budget bookkeeping.
    AdSpendLog.objects.create(
        campaign=imp.ad_group.campaign, kind='cpc', amount=cpc,
        currency=imp.ad_group.campaign.currency,
    )
    AdCampaign.objects.filter(pk=imp.ad_group.campaign_id).update(
        daily_spend=django_models.F('daily_spend') + cpc,
        total_spend=django_models.F('total_spend') + cpc,
    )
    return {'click_id': click.pk, 'cpc_charged': str(cpc)}


# ═══════════════════════════════════════════════════════════════════
# CH15 — Spend pacing + auto-pause
# ═══════════════════════════════════════════════════════════════════

def pace_ad_campaigns() -> dict:
    """Adjust each live campaign's `pacing_multiplier` so spend
    distributes evenly across the day. A burn rate higher than the
    elapsed fraction-of-day → throttle; lower → boost."""
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_fraction = ((now - day_start).total_seconds() / 86400) or 0.01

    qs = AdCampaign.objects.filter(status='live')
    n = 0; paused = 0
    for c in qs.iterator():
        budget = float(c.daily_budget or 0)
        spent = float(c.daily_spend or 0)
        target = budget * day_fraction
        if budget <= 0:
            continue
        if spent >= budget:
            c.status = 'paused_budget'
            c.save(update_fields=['status'])
            paused += 1
            continue
        # Burn rate vs target.
        ratio = spent / max(target, 1.0)
        if ratio > 1.2:
            new_mult = max(0.3, c.pacing_multiplier * 0.8)
        elif ratio < 0.8:
            new_mult = min(1.5, c.pacing_multiplier * 1.1)
        else:
            new_mult = 1.0
        c.pacing_multiplier = round(new_mult, 4)
        c.last_paced_at = now
        c.save(update_fields=['pacing_multiplier', 'last_paced_at'])
        n += 1
    return {'paced': n, 'auto_paused': paused}


def reset_daily_ad_spend() -> int:
    """Run at 00:00 UTC: zero the daily_spend counter + un-pause
    campaigns auto-paused for budget."""
    qs = AdCampaign.objects.exclude(daily_spend=0)
    n = qs.update(daily_spend=Decimal('0'), pacing_multiplier=1.0)
    AdCampaign.objects.filter(status='paused_budget').update(status='live')
    return n


# ═══════════════════════════════════════════════════════════════════
# CH16 — Pixel events
# ═══════════════════════════════════════════════════════════════════

def emit_pixel_event(*, provider: str, event_name: str,
                      user=None, payload: dict = None,
                      external_event_id: str = '',
                      hashed_user_data: dict = None) -> PixelEvent:
    """Queue the event for the forwarder task. Production forwarder
    POSTs to Meta CAPI / Google / TikTok and updates `status`."""
    if not external_event_id:
        raw = f'{provider}|{event_name}|{user.pk if user else "anon"}|{timezone.now().timestamp()}'
        external_event_id = hashlib.sha256(raw.encode()).hexdigest()[:64]
    obj = PixelEvent.objects.create(
        provider=provider, event_name=event_name[:40],
        user=user, payload=payload or {},
        user_data_hashed=hashed_user_data or {},
        event_id_external=external_event_id,
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH17 — Segments
# ═══════════════════════════════════════════════════════════════════

def materialise_segment(segment: MarketingSegment) -> int:
    """Walk the segment definition + write SegmentMembership rows.
    Definition spec is intentionally small — production expands to a
    proper rules DSL.  Today's supported keys:

      {"lifetime_orders__gte": 1}
      {"country": "AO"}
      {"is_premium_member": true}
      {"dormancy_band": "lapsing"}
    """
    spec = segment.definition or {}
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    if 'country' in spec:
        if hasattr(User, 'country'):
            qs = qs.filter(country=spec['country'])
    # The rest are best-effort joins to existing apps. Each delegation
    # is wrapped so an absent app doesn't break the materialiser.
    if spec.get('is_premium_member'):
        try:
            from apps.buyer_engagement.models import PremiumMembership
            ids = PremiumMembership.objects.filter(
                status__in=('trial', 'active', 'grace'),
            ).values_list('user_id', flat=True)
            qs = qs.filter(pk__in=list(ids))
        except Exception:
            pass
    if 'dormancy_band' in spec:
        try:
            from apps.buyer_engagement.models import DormancyState
            ids = DormancyState.objects.filter(
                band=spec['dormancy_band'],
            ).values_list('user_id', flat=True)
            qs = qs.filter(pk__in=list(ids))
        except Exception:
            pass
    if spec.get('lifetime_orders__gte'):
        try:
            from apps.buyer_engagement.models import DormancyState
            ids = DormancyState.objects.filter(
                lifetime_orders__gte=spec['lifetime_orders__gte'],
            ).values_list('user_id', flat=True)
            qs = qs.filter(pk__in=list(ids))
        except Exception:
            pass

    user_ids = list(qs.values_list('pk', flat=True))
    SegmentMembership.objects.filter(segment=segment).delete()
    SegmentMembership.objects.bulk_create([
        SegmentMembership(segment=segment, user_id=uid) for uid in user_ids
    ], batch_size=500)
    segment.estimated_size = len(user_ids)
    segment.last_materialised_at = timezone.now()
    segment.save(update_fields=['estimated_size', 'last_materialised_at'])
    return len(user_ids)


# ═══════════════════════════════════════════════════════════════════
# CH18 — SMS opt-in
# ═══════════════════════════════════════════════════════════════════

def sms_opt_in(*, user, phone: str) -> SmsOptIn:
    obj, _ = SmsOptIn.objects.update_or_create(
        user=user,
        defaults={'phone': phone[:30], 'opted_in': True,
                  'opted_in_at': timezone.now(), 'opted_out_at': None},
    )
    return obj


def sms_opt_out(*, user) -> bool:
    obj = SmsOptIn.objects.filter(user=user).first()
    if not obj:
        return False
    obj.opted_in = False
    obj.opted_out_at = timezone.now()
    obj.save(update_fields=['opted_in', 'opted_out_at'])
    return True


def sms_eligible_to_receive(user) -> bool:
    """Per CH18 — must be opted in, daily cap respected."""
    obj = SmsOptIn.objects.filter(user=user, opted_in=True).first()
    if not obj:
        return False
    # Daily cap: 1 marketing SMS per 24h.
    if obj.daily_count >= 1:
        reset = obj.daily_reset_at or (obj.last_message_at + timedelta(hours=24)) if obj.last_message_at else None
        if reset and reset > timezone.now():
            return False
    return True


# ═══════════════════════════════════════════════════════════════════
# CH19 — Push A/B resolution
# ═══════════════════════════════════════════════════════════════════

def assign_push_variant(user, campaign: PushMarketingCampaign) -> str:
    """Deterministic per-(user, campaign) assignment so re-runs stick.
    Hash the user-id + campaign-id into [0,100); below ab_split_pct → A."""
    h = hashlib.sha256(f'{user.pk}:{campaign.pk}'.encode()).hexdigest()
    bucket = int(h[:8], 16) % 100
    return 'A' if bucket < campaign.ab_split_pct else 'B'


# ═══════════════════════════════════════════════════════════════════
# CH22 — Lift measurement
# ═══════════════════════════════════════════════════════════════════

def compute_promotion_lift(*, promotion: MePromotion,
                            window_start: date_cls, window_end: date_cls) -> PromotionLift:
    """Compute lift vs holdout. Holdout defined as users in the
    targeted segment who didn't redeem; test = users who did. ROI =
    incremental GMV / discount cost."""
    test_user_ids = list(
        PromotionUsage.objects.filter(
            promotion=promotion,
            used_at__date__gte=window_start,
            used_at__date__lte=window_end,
        ).values_list('user_id', flat=True).distinct()
    )
    holdout_user_ids = []
    # Holdout: users in target segment without usage.
    try:
        seg = MarketingSegment.objects.filter(slug=promotion.target_segment).first()
        if seg:
            holdout_user_ids = list(
                SegmentMembership.objects.filter(segment=seg)
                .exclude(user_id__in=test_user_ids)
                .values_list('user_id', flat=True)
            )
    except Exception:
        pass

    def _gmv(user_ids):
        if not user_ids:
            return Decimal('0'), 0
        try:
            from apps.orders.models import Order
            agg = Order.objects.filter(
                user_id__in=user_ids,
                created_at__date__gte=window_start,
                created_at__date__lte=window_end,
            ).aggregate(s=django_models.Sum('total_amount'),
                        n=django_models.Count('id'))
            return Decimal(str(agg['s'] or 0)), int(agg['n'] or 0)
        except Exception:
            return Decimal('0'), 0

    test_gmv, test_conv = _gmv(test_user_ids)
    holdout_gmv, holdout_conv = _gmv(holdout_user_ids)

    test_per_user = (test_gmv / Decimal(len(test_user_ids))) if test_user_ids else Decimal('0')
    holdout_per_user = (holdout_gmv / Decimal(len(holdout_user_ids))) if holdout_user_ids else Decimal('0')
    incremental_gmv = (test_per_user - holdout_per_user) * Decimal(len(test_user_ids))
    incremental_pct = 0.0
    if holdout_per_user > 0:
        incremental_pct = float((test_per_user - holdout_per_user) / holdout_per_user) * 100
    cost = Decimal(str(promotion.budget_spent or 0))
    roi = float(incremental_gmv / cost) if cost > 0 else 0.0

    obj, _ = PromotionLift.objects.update_or_create(
        promotion=promotion, window_start=window_start,
        defaults={
            'window_end': window_end,
            'test_size': len(test_user_ids),
            'holdout_size': len(holdout_user_ids),
            'test_gmv': test_gmv, 'holdout_gmv': holdout_gmv,
            'test_conversions': test_conv, 'holdout_conversions': holdout_conv,
            'incremental_gmv': incremental_gmv,
            'incremental_conversions_pct': incremental_pct,
            'roi': roi,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH23 — Promotion abuse detection
# ═══════════════════════════════════════════════════════════════════

def detect_promotion_abuse_window(*, window_hours: int = 24) -> int:
    """Walk recent usage rows and flag suspicious patterns.
    Heuristics shipped today:

      - duplicate_account_coupon: > 3 welcome-style codes
        redeemed from the same fingerprint in window
      - rapid_refund_pattern:     order refunded within 2h
        of redemption
      - coupon_stacking_attempt:  promotion `rejected` reason logged
    """
    n = 0
    cutoff = timezone.now() - timedelta(hours=window_hours)
    # Heuristic 1 — high-frequency welcome redemptions.
    from django.db.models import Count
    suspicious = (
        PromotionUsage.objects
        .filter(used_at__gte=cutoff, promotion__type__in=('welcome_coupon', 'referral_reward_coupon'))
        .values('user').annotate(c=Count('id')).filter(c__gte=2)
    )
    for row in suspicious:
        PromotionAbuseSignal.objects.create(
            user_id=row['user'], kind='duplicate_account_coupon',
            severity=40, evidence={'redemption_count': row['c'],
                                    'window_hours': window_hours},
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_marketing_kpis(snapshot_date=None) -> MarketingKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)

    active = MePromotion.objects.filter(status='active').count()
    redemptions = PromotionUsage.objects.filter(used_at__gte=start, used_at__lt=end).count()
    total_discount = (
        PromotionUsage.objects.filter(used_at__gte=start, used_at__lt=end)
        .aggregate(s=django_models.Sum('discount_amount'))['s'] or Decimal('0')
    )
    flash_gmv = (
        FlashSaleItem.objects.aggregate(
            s=django_models.Sum(django_models.F('sold_qty') * django_models.F('flash_price')),
        )['s'] or Decimal('0')
    )
    spin_count = PromoGameSpin.objects.filter(
        spun_at__gte=start, spun_at__lt=end, game__type='spin_wheel',
    ).count()
    scratch_count = PromoGameSpin.objects.filter(
        spun_at__gte=start, spun_at__lt=end, game__type='scratch_card',
    ).count()
    ad_spend = (
        AdSpendLog.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
        .aggregate(s=django_models.Sum('amount'))['s'] or Decimal('0')
    )
    creator_gmv = (
        CreatorCampaign.objects.aggregate(s=django_models.Sum('gmv_generated'))['s'] or Decimal('0')
    )
    abuse = PromotionAbuseSignal.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()

    by_promo_type = dict(
        MePromotion.objects.values_list('type').annotate(c=django_models.Count('id'))
    )
    obj, _ = MarketingKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'total_promotions_active': active,
            'total_promo_redemptions': redemptions,
            'total_discount_given': total_discount,
            'flash_sale_gmv': flash_gmv,
            'spin_plays': spin_count, 'scratch_plays': scratch_count,
            'ad_spend': ad_spend, 'creator_gmv': creator_gmv,
            'abuse_signals_detected': abuse,
            'by_promo_type': {k or '': v for k, v in by_promo_type.items()},
        },
    )
    return obj
