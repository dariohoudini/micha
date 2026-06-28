"""
Promotions & Marketing Engine data model
=========================================

Implements AliExpress_Promotions_Marketing_Engine.docx CH1-CH24 at
the DB layer. Existing apps that already cover parts of this domain
are intentionally NOT duplicated — we extend them with this app's
unified Promotion table + the auction/games/pixel/campaign rows that
have no home today.

  CH1.2  MePromotion              — unified promotion catalogue (12 types)
                                    Prefixed "Me" to avoid collision with
                                    the legacy promotions.Coupon model.
  CH1.2  PromotionUsage           — per-user / per-order redemption ledger
  CH4    FlashSaleApplication     — seller's request to join a platform sale
  CH5    FlashSaleItem            — allocated_qty / sold_qty / reserved_qty FSM
  CH6    BundleDeal               — fixed / buy_x_get_y / complement
  CH7    VolumeDiscount           — tier ladder per product
  CH8    FreeGiftPromotion        — qualifying product → gift attachment
  CH10   PromoGame, PromoGamePrize, PromoGameSpin — spin/scratch
         + ShareScratchEvent      — viral loop attribution
  CH13   CreatorAccount, CreatorCampaign — influencer programme
  CH14   AdCampaign, AdGroup, AdKeyword, AdImpression, AdClick — sponsored
  CH15   AdBudget, AdSpendLog     — budget pacing + auto-pause
  CH16   PixelEvent               — Meta/Google/TikTok forward log
  CH17   MarketingSegment, EmailMarketingCampaign
  CH18   SmsOptIn, SmsCampaign
  CH19   PushMarketingCampaign, PushCampaignVariant — A/B
  CH20   SuperDealsCampaign, SuperDealsEnrolment
  CH21   CoMarketingPartner, CoMarketingCampaign
  CH22   PromotionLift            — lift vs holdout
  CH23   PromotionAbuseSignal     — fraud detection on promo abuse
  CH24   MarketingKpiSnapshot     — daily KPI roll-up
  Audit  MarketingEvent           — append-only per-user / per-promo audit

Every state change writes a MarketingEvent row.
"""
from __future__ import annotations

import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────
# CH1 — Unified promotion taxonomy
# ─────────────────────────────────────────────────────────────────

PROMOTION_TYPE_CHOICES = (
    ('platform_coupon',       'Platform coupon'),
    ('seller_coupon',         'Seller coupon'),
    ('product_coupon',        'Product coupon'),
    ('flash_sale_price',      'Flash sale price'),
    ('bundle_deal',           'Bundle deal'),
    ('volume_discount',       'Volume discount'),
    ('free_gift',             'Free gift'),
    ('coins_discount',        'Coins discount'),
    ('free_shipping_coupon',  'Free shipping coupon'),
    ('welcome_coupon',        'Welcome coupon'),
    ('referral_reward_coupon','Referral reward'),
    ('cashback',              'Cashback'),
    ('event_coupon',          'Event coupon'),
    ('bnpl',                  'BNPL promotion'),
)

PROMOTION_STATUS_CHOICES = (
    ('draft',     'Draft'),
    ('scheduled', 'Scheduled'),
    ('active',    'Active'),
    ('paused',    'Paused'),
    ('ended',     'Ended'),
    ('cancelled', 'Cancelled'),
)

FUNDED_BY_CHOICES = (
    ('platform', 'Platform'),
    ('seller',   'Seller'),
    ('shared',   'Shared platform+seller'),
)

DISCOUNT_TYPE_CHOICES = (
    ('percentage',    'Percentage off'),
    ('fixed_amount',  'Fixed amount off'),
    ('free_shipping', 'Free shipping'),
    ('free_item',     'Free item'),
)

DISTRIBUTION_METHOD_CHOICES = (
    ('public',   'Public — coupon centre'),
    ('targeted', 'Targeted — pushed to segment'),
    ('code_only','Code only — buyer enters at checkout'),
)


class MePromotion(models.Model):
    """The unified promotion record matching CH1.2 spec.

    The "Me" prefix dodges the existing apps.promotions.Coupon /
    FlashSale tables — those remain for the legacy coupon flow.
    New promo types route through this table.

    Stackability rules live in services.STACKABILITY_RULES rather
    than the DB so they can ship as code changes (more auditable +
    safer against accidental admin edits)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=24, choices=PROMOTION_TYPE_CHOICES, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    funded_by = models.CharField(max_length=10, choices=FUNDED_BY_CHOICES, default='platform')
    funding_split_pct = models.PositiveSmallIntegerField(null=True, blank=True)

    # Scope.
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_promotions',
        help_text='NULL = platform-wide',
    )
    product_ids = models.JSONField(default=list, blank=True)
    category_ids = models.JSONField(default=list, blank=True)

    # Discount definition.
    discount_type = models.CharField(max_length=16, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    max_discount_cap = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_quantity = models.PositiveIntegerField(default=1)

    # Eligibility.
    eligible_user_types = models.JSONField(default=list, blank=True)
    eligible_countries = models.JSONField(default=list, blank=True)
    requires_coupon_code = models.BooleanField(default=False)
    coupon_code = models.CharField(max_length=50, blank=True, default='', db_index=True)
    distribution_method = models.CharField(
        max_length=12, choices=DISTRIBUTION_METHOD_CHOICES, default='public',
    )
    target_segment = models.CharField(max_length=80, blank=True, default='')
    max_uses_total = models.PositiveIntegerField(null=True, blank=True)
    max_uses_per_user = models.PositiveSmallIntegerField(default=1)

    # Validity.
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(
        max_length=12, choices=PROMOTION_STATUS_CHOICES, default='draft', db_index=True,
    )

    # Budget.
    max_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    budget_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    uses_count = models.PositiveIntegerField(default=0)

    # Stackability override — defaults loaded from services.STACKABILITY_RULES.
    non_stackable_with = models.JSONField(default=list, blank=True)
    priority_score = models.PositiveSmallIntegerField(
        default=50,
        help_text='Tie-breaker for priority resolution. Higher = preferred.',
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_promotions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type', 'status']),
            models.Index(fields=['valid_from', 'valid_until']),
            models.Index(fields=['seller', 'status']),
        ]


class PromotionUsage(models.Model):
    """Per-user, per-order usage record. The atomic redemption at
    order placement creates this row inside a transaction so a race
    between two concurrent checkouts can't double-use the same
    coupon."""

    id = models.BigAutoField(primary_key=True)
    promotion = models.ForeignKey(MePromotion, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promotion_usages')
    order_id = models.CharField(max_length=64, blank=True, default='')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    used_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = [('promotion', 'order_id')]
        indexes = [models.Index(fields=['user', 'promotion'])]


# ─────────────────────────────────────────────────────────────────
# CH4 / CH5 — Flash sale application + inventory reservation
# ─────────────────────────────────────────────────────────────────

FLASH_APPLICATION_STATUS_CHOICES = (
    ('draft',     'Draft'),
    ('submitted', 'Submitted'),
    ('approved',  'Approved'),
    ('rejected',  'Rejected'),
    ('cancelled', 'Cancelled'),
)


class FlashSaleApplication(models.Model):
    """Seller's application to join a platform-organised flash sale.
    Auto-validated by CH4.1 gates, then human-reviewed by
    merchandising team."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flash_sale_applications')
    event_slug = models.CharField(max_length=64, db_index=True)
    products = models.JSONField(default=list, blank=True)  # [{product_id, sku_id, normal_price, ...}]
    delivery_guarantee = models.CharField(
        max_length=16,
        choices=(('5_days', '5 days'), ('10_days', '10 days'), ('standard', 'Standard')),
        default='standard',
    )
    seller_notes = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=12, choices=FLASH_APPLICATION_STATUS_CHOICES, default='draft',
    )
    auto_validation_passed = models.BooleanField(default=False)
    auto_validation_errors = models.JSONField(default=list, blank=True)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_flash_applications',
    )
    rejection_reason = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FlashSaleItem(models.Model):
    """The actual flash-sale inventory row consumed by the buyer
    side. `available_qty` is computed from allocated - sold -
    reserved at read time; the FSM updates are done with FOR UPDATE
    inside a transaction (CH5.1) so two concurrent checkouts can't
    oversell."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        FlashSaleApplication, on_delete=models.CASCADE, related_name='items',
    )
    event_slug = models.CharField(max_length=64, db_index=True)
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    normal_price = models.DecimalField(max_digits=10, decimal_places=2)
    flash_price = models.DecimalField(max_digits=10, decimal_places=2)
    allocated_qty = models.PositiveIntegerField()
    sold_qty = models.PositiveIntegerField(default=0)
    reserved_qty = models.PositiveIntegerField(default=0)
    self_funded = models.BooleanField(default=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['event_slug', 'product_id']),
        ]

    @property
    def available_qty(self) -> int:
        return max(0, self.allocated_qty - self.sold_qty - self.reserved_qty)

    @property
    def claimed_pct(self) -> float:
        return (self.sold_qty / self.allocated_qty * 100) if self.allocated_qty else 0


class FlashSaleReservation(models.Model):
    """Outstanding reservation against a FlashSaleItem. Expires at
    `expires_at` and is released by the sweeper task."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(FlashSaleItem, on_delete=models.CASCADE, related_name='reservations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flash_reservations')
    quantity = models.PositiveIntegerField()
    checkout_session_id = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(
        max_length=12, default='active',
        choices=(('active', 'Active'), ('confirmed', 'Confirmed'),
                 ('released', 'Released'), ('expired', 'Expired')),
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'expires_at'])]


# ─────────────────────────────────────────────────────────────────
# CH6 — Bundle deals
# ─────────────────────────────────────────────────────────────────

BUNDLE_TYPE_CHOICES = (
    ('fixed_bundle',     'Fixed bundle'),
    ('buy_x_get_y',      'Buy X get Y'),
    ('complement_bundle','Complement bundle'),
)


class BundleDeal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bundle_deals')
    name = models.CharField(max_length=200)
    bundle_type = models.CharField(max_length=20, choices=BUNDLE_TYPE_CHOICES)
    components = models.JSONField(default=list)
    bundle_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_type = models.CharField(
        max_length=16,
        choices=(('fixed_price', 'Fixed price'),
                 ('percentage', 'Percentage off'),
                 ('fixed_amount', 'Fixed amount off')),
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    min_bundle_savings_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.0'))
    stock_limit = models.PositiveIntegerField(null=True, blank=True)
    claims_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('active', 'Active'),
                 ('paused', 'Paused'), ('ended', 'Ended')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH7 — Volume discount
# ─────────────────────────────────────────────────────────────────

class VolumeDiscount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='volume_discounts')
    product_id = models.CharField(max_length=64, db_index=True)
    tiers = models.JSONField(default=list)
    # tiers: [{min_quantity:2, max_quantity:4, discount_pct:5.0}, ...]
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='active',
        choices=(('active', 'Active'), ('paused', 'Paused'), ('ended', 'Ended')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH8 — Free gift
# ─────────────────────────────────────────────────────────────────

class FreeGiftPromotion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='free_gift_promotions')
    qualifying_product_id = models.CharField(max_length=64, db_index=True)
    qualifying_min_qty = models.PositiveSmallIntegerField(default=1)
    qualifying_min_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gift_product_id = models.CharField(max_length=64)
    gift_sku_id = models.CharField(max_length=64, blank=True, default='')
    gift_quantity = models.PositiveSmallIntegerField(default=1)
    gift_stock_allocated = models.PositiveIntegerField()
    gift_stock_remaining = models.PositiveIntegerField()
    max_per_order = models.PositiveSmallIntegerField(default=1)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='active',
        choices=(('active', 'Active'), ('paused', 'Paused'),
                 ('ended', 'Ended'), ('sold_out', 'Sold out')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH10 — Promo games (spin wheel + scratch card)
# ─────────────────────────────────────────────────────────────────

GAME_TYPE_CHOICES = (
    ('spin_wheel',   'Spin the wheel'),
    ('scratch_card', 'Scratch card'),
)

PRIZE_TYPE_CHOICES = (
    ('coupon',       'Coupon'),
    ('coins',        'Coins'),
    ('free_product', 'Free product'),
    ('cashback',     'Cashback'),
    ('better_luck',  'Better luck next time'),
)


class PromoGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=16, choices=GAME_TYPE_CHOICES)
    name = models.CharField(max_length=120)
    event_slug = models.CharField(max_length=64, blank=True, default='', db_index=True)
    spins_per_user_per_day = models.PositiveSmallIntegerField(default=3)
    extra_spin_price_coins = models.PositiveIntegerField(default=20)
    eligibility = models.CharField(max_length=80, default='all')
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='active',
        choices=(('active', 'Active'), ('paused', 'Paused'), ('ended', 'Ended')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


class PromoGamePrize(models.Model):
    id = models.BigAutoField(primary_key=True)
    game = models.ForeignKey(PromoGame, on_delete=models.CASCADE, related_name='prizes')
    prize_type = models.CharField(max_length=16, choices=PRIZE_TYPE_CHOICES)
    label = models.CharField(max_length=80, blank=True, default='')
    coupon_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_min_order = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coins_amount = models.PositiveIntegerField(default=0)
    product_id = models.CharField(max_length=64, blank=True, default='')
    probability = models.DecimalField(
        max_digits=5, decimal_places=4,
        help_text='0.0–1.0; sum across prizes ~= 1.0',
    )
    stock = models.PositiveIntegerField(null=True, blank=True)
    stock_remaining = models.PositiveIntegerField(null=True, blank=True)
    is_fallback = models.BooleanField(
        default=False,
        help_text='Picked when a higher-probability prize is out of stock',
    )


class PromoGameSpin(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_game_spins')
    game = models.ForeignKey(PromoGame, on_delete=models.CASCADE, related_name='spins')
    outcome_prize = models.ForeignKey(
        PromoGamePrize, on_delete=models.SET_NULL, null=True, blank=True,
    )
    outcome_label = models.CharField(max_length=80, blank=True, default='')
    spent_coins = models.PositiveIntegerField(default=0)
    was_extra_spin = models.BooleanField(default=False)
    delivered = models.BooleanField(default=False)
    delivery_payload = models.JSONField(default=dict, blank=True)
    spun_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'game', 'spun_at'])]


class ShareScratchEvent(models.Model):
    """CH10.2 viral loop — each share generates a token, and a
    converted referee credits one extra scratch to both sides."""

    id = models.BigAutoField(primary_key=True)
    sharer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scratch_shares_sent')
    game = models.ForeignKey(PromoGame, on_delete=models.CASCADE, related_name='scratch_shares')
    share_token = models.CharField(max_length=32, unique=True, db_index=True)
    referee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scratch_shares_received',
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def make_token():
        return secrets.token_urlsafe(16)[:32]


# ─────────────────────────────────────────────────────────────────
# CH13 — Creator / influencer programme
# ─────────────────────────────────────────────────────────────────

CREATOR_TIER_CHOICES = (
    ('nano',  'Nano (1k-10k followers)'),
    ('micro', 'Micro (10k-100k)'),
    ('mid',   'Mid (100k-1M)'),
    ('macro', 'Macro (1M+)'),
)


class CreatorAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='creator_account')
    handle = models.CharField(max_length=80, unique=True)
    tier = models.CharField(max_length=8, choices=CREATOR_TIER_CHOICES, default='nano')
    primary_platform = models.CharField(max_length=24, default='instagram')
    followers_count = models.PositiveIntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)
    primary_category = models.CharField(max_length=80, blank=True, default='')
    country = models.CharField(max_length=2, default='AO')
    status = models.CharField(
        max_length=12, default='pending',
        choices=(('pending', 'Pending'), ('active', 'Active'),
                 ('suspended', 'Suspended'), ('terminated', 'Terminated')),
    )
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.0'))
    created_at = models.DateTimeField(auto_now_add=True)


class CreatorCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(CreatorAccount, on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=160)
    product_ids = models.JSONField(default=list)
    tracking_code = models.CharField(max_length=24, unique=True, db_index=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    gmv_generated = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_owed = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=12, default='live',
        choices=(('live', 'Live'), ('ended', 'Ended'), ('paused', 'Paused')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH14 — Sponsored ads (auction model)
# ─────────────────────────────────────────────────────────────────

AD_CAMPAIGN_STATUS_CHOICES = (
    ('draft',         'Draft'),
    ('scheduled',     'Scheduled'),
    ('live',          'Live'),
    ('paused',        'Paused — manual'),
    ('paused_budget', 'Paused — budget exhausted'),
    ('ended',         'Ended'),
)

BID_STRATEGY_CHOICES = (
    ('manual_cpc',     'Manual CPC'),
    ('auto_max_clicks','Auto — max clicks'),
    ('auto_max_roas',  'Auto — max ROAS'),
)


class AdCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad_campaigns')
    name = models.CharField(max_length=160)
    objective = models.CharField(
        max_length=24,
        choices=(('sales', 'Sales'), ('traffic', 'Traffic'),
                 ('awareness', 'Awareness'), ('install', 'App install')),
        default='sales',
    )
    bid_strategy = models.CharField(max_length=24, choices=BID_STRATEGY_CHOICES, default='manual_cpc')
    daily_budget = models.DecimalField(max_digits=10, decimal_places=2)
    total_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='AOA')
    daily_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=AD_CAMPAIGN_STATUS_CHOICES, default='draft', db_index=True,
    )
    last_paced_at = models.DateTimeField(null=True, blank=True)
    pacing_multiplier = models.FloatField(
        default=1.0,
        help_text='Throttle factor 0..1 applied by the spend-pacing algorithm.',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AdGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name='ad_groups')
    name = models.CharField(max_length=160)
    product_id = models.CharField(max_length=64, db_index=True)
    bid_amount = models.DecimalField(max_digits=10, decimal_places=4)
    quality_score = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(
        max_length=12, default='active',
        choices=(('active', 'Active'), ('paused', 'Paused')),
    )


class AdKeyword(models.Model):
    id = models.BigAutoField(primary_key=True)
    ad_group = models.ForeignKey(AdGroup, on_delete=models.CASCADE, related_name='keywords')
    keyword = models.CharField(max_length=120, db_index=True)
    match_type = models.CharField(
        max_length=12, default='broad',
        choices=(('exact', 'Exact'), ('phrase', 'Phrase'),
                 ('broad', 'Broad')),
    )
    bid_override = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)


class AdImpression(models.Model):
    id = models.BigAutoField(primary_key=True)
    ad_group = models.ForeignKey(AdGroup, on_delete=models.CASCADE, related_name='impressions')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ad_impressions',
    )
    placement = models.CharField(max_length=24, blank=True, default='')
    search_query = models.CharField(max_length=200, blank=True, default='')
    ad_rank = models.FloatField(default=0)
    cpm_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


class AdClick(models.Model):
    id = models.BigAutoField(primary_key=True)
    ad_group = models.ForeignKey(AdGroup, on_delete=models.CASCADE, related_name='clicks')
    impression = models.ForeignKey(
        AdImpression, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='clicks',
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ad_clicks',
    )
    cpc_cost = models.DecimalField(max_digits=10, decimal_places=4)
    converted = models.BooleanField(default=False)
    conversion_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — Ad budget pacing + auto-pause
# ─────────────────────────────────────────────────────────────────

class AdSpendLog(models.Model):
    """Append-only per-charge spend log. Used both for billing and for
    the pacing algorithm to compute hourly burn rate."""

    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name='spend_logs')
    kind = models.CharField(
        max_length=12, choices=(('cpc', 'CPC'), ('cpm', 'CPM')),
        default='cpc',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=4)
    currency = models.CharField(max_length=3, default='AOA')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH16 — Retargeting pixel events
# ─────────────────────────────────────────────────────────────────

PIXEL_PROVIDER_CHOICES = (
    ('meta',   'Meta (Facebook) CAPI'),
    ('google', 'Google Ads / Enhanced Conversions'),
    ('tiktok', 'TikTok Events API'),
    ('snap',   'Snap'),
    ('reddit', 'Reddit'),
)


class PixelEvent(models.Model):
    """Every server-side conversion event forwarded to a paid-media
    pixel lands here. Production pushes from this table to the
    provider; failures are retried by the forwarder task."""

    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=12, choices=PIXEL_PROVIDER_CHOICES, db_index=True)
    event_name = models.CharField(max_length=40, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pixel_events',
    )
    event_id_external = models.CharField(
        max_length=80, db_index=True,
        help_text='Idempotency key sent to provider for dedup',
    )
    payload = models.JSONField(default=dict)
    user_data_hashed = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=12, default='queued',
        choices=(('queued', 'Queued'), ('sent', 'Sent'),
                 ('failed', 'Failed'), ('skipped', 'Skipped — consent')),
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH17 — Audience segments + email campaign builder
# ─────────────────────────────────────────────────────────────────

class MarketingSegment(models.Model):
    """A reusable buyer segment. `definition` is a JSON spec (operator,
    field, value) compiled to a queryset by services.resolve_segment.
    Snapshot rows write the materialised user IDs for fast lookups."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    definition = models.JSONField(default=dict)
    estimated_size = models.PositiveIntegerField(default=0)
    last_materialised_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SegmentMembership(models.Model):
    id = models.BigAutoField(primary_key=True)
    segment = models.ForeignKey(MarketingSegment, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='segment_memberships')
    snapshot_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('segment', 'user')]


class EmailMarketingCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    segment = models.ForeignKey(MarketingSegment, on_delete=models.PROTECT, related_name='email_campaigns')
    template_key = models.CharField(max_length=64)
    subject_override = models.CharField(max_length=255, blank=True, default='')
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('scheduled', 'Scheduled'),
                 ('sending', 'Sending'), ('sent', 'Sent'),
                 ('cancelled', 'Cancelled')),
    )
    queued_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    opened_count = models.PositiveIntegerField(default=0)
    clicked_count = models.PositiveIntegerField(default=0)
    revenue_attributed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — SMS opt-in + campaigns
# ─────────────────────────────────────────────────────────────────

class SmsOptIn(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='sms_opt_in')
    phone = models.CharField(max_length=30)
    opted_in = models.BooleanField(default=False)
    opted_in_at = models.DateTimeField(null=True, blank=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    daily_count = models.PositiveSmallIntegerField(default=0)
    daily_reset_at = models.DateTimeField(null=True, blank=True)


class SmsCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    segment = models.ForeignKey(MarketingSegment, on_delete=models.PROTECT, related_name='sms_campaigns')
    body = models.CharField(max_length=160)
    deep_link = models.CharField(max_length=255, blank=True, default='')
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('scheduled', 'Scheduled'),
                 ('sending', 'Sending'), ('sent', 'Sent'),
                 ('cancelled', 'Cancelled')),
    )
    queued_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    suppressed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH19 — Push campaigns with A/B
# ─────────────────────────────────────────────────────────────────

class PushMarketingCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    segment = models.ForeignKey(MarketingSegment, on_delete=models.PROTECT, related_name='push_campaigns')
    ab_split_pct = models.PositiveSmallIntegerField(
        default=50,
        help_text='Pct of segment in variant A; remainder in B.',
    )
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('scheduled', 'Scheduled'),
                 ('sending', 'Sending'), ('sent', 'Sent')),
    )
    winner_variant = models.CharField(max_length=1, blank=True, default='')
    queued_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    opened_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class PushCampaignVariant(models.Model):
    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(PushMarketingCampaign, on_delete=models.CASCADE, related_name='variants')
    variant_key = models.CharField(max_length=1, default='A')
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=240)
    deep_link = models.CharField(max_length=255, blank=True, default='')
    sent_count = models.PositiveIntegerField(default=0)
    opened_count = models.PositiveIntegerField(default=0)
    clicked_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('campaign', 'variant_key')]


# ─────────────────────────────────────────────────────────────────
# CH20 — Super Deals
# ─────────────────────────────────────────────────────────────────

class SuperDealsCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    country_scope = models.JSONField(default=list, blank=True)
    discount_floor_pct = models.PositiveSmallIntegerField(default=30)
    visibility_multiplier = models.FloatField(default=2.0)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('scheduled', 'Scheduled'),
                 ('live', 'Live'), ('ended', 'Ended')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


class SuperDealsEnrolment(models.Model):
    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(SuperDealsCampaign, on_delete=models.CASCADE, related_name='enrolments')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='super_deal_enrolments')
    product_ids = models.JSONField(default=list)
    status = models.CharField(
        max_length=12, default='pending',
        choices=(('pending', 'Pending'), ('approved', 'Approved'),
                 ('rejected', 'Rejected'), ('live', 'Live')),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('campaign', 'seller')]


# ─────────────────────────────────────────────────────────────────
# CH21 — Co-marketing / brand partnership
# ─────────────────────────────────────────────────────────────────

class CoMarketingPartner(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=160)
    industry = models.CharField(max_length=80, blank=True, default='')
    country = models.CharField(max_length=2, blank=True, default='')
    contact_email = models.EmailField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CoMarketingCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.ForeignKey(CoMarketingPartner, on_delete=models.PROTECT, related_name='campaigns')
    name = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    budget_split = models.JSONField(
        default=dict, blank=True,
        help_text='{"micha":50, "partner":50} percentage of campaign cost.',
    )
    deliverables = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('scheduled', 'Scheduled'),
                 ('live', 'Live'), ('ended', 'Ended')),
    )
    revenue_attributed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Promotion lift measurement
# ─────────────────────────────────────────────────────────────────

class PromotionLift(models.Model):
    """Incremental-lift result for a promotion vs a holdout group."""

    id = models.BigAutoField(primary_key=True)
    promotion = models.ForeignKey(MePromotion, on_delete=models.CASCADE, related_name='lift_results')
    window_start = models.DateField()
    window_end = models.DateField()
    test_size = models.PositiveIntegerField(default=0)
    holdout_size = models.PositiveIntegerField(default=0)
    test_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    holdout_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    test_conversions = models.PositiveIntegerField(default=0)
    holdout_conversions = models.PositiveIntegerField(default=0)
    incremental_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    incremental_conversions_pct = models.FloatField(default=0)
    roi = models.FloatField(default=0)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('promotion', 'window_start')]


# ─────────────────────────────────────────────────────────────────
# CH23 — Promotion abuse signals
# ─────────────────────────────────────────────────────────────────

ABUSE_KIND_CHOICES = (
    ('duplicate_account_coupon',  'Duplicate account abuse'),
    ('rapid_refund_pattern',      'Refund-after-coupon pattern'),
    ('referral_self_loop',        'Self-referral loop'),
    ('coupon_stacking_attempt',   'Attempted forbidden stack'),
    ('cart_padding_for_min_order','Cart padding to clear min-order'),
    ('cancel_after_discount',     'Cancel-after-discount pattern'),
)


class PromotionAbuseSignal(models.Model):
    """Each detected abuse pattern fires a row. The abuse engine
    aggregates them per user and decides downstream action."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_abuse_signals')
    promotion = models.ForeignKey(
        MePromotion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='abuse_signals',
    )
    kind = models.CharField(max_length=32, choices=ABUSE_KIND_CHOICES, db_index=True)
    severity = models.PositiveSmallIntegerField(
        default=10,
        help_text='Per-signal weight; aggregated to user-level abuse score.',
    )
    evidence = models.JSONField(default=dict, blank=True)
    action_taken = models.CharField(max_length=80, blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — Marketing KPI snapshot
# ─────────────────────────────────────────────────────────────────

class MarketingKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    total_promotions_active = models.PositiveIntegerField(default=0)
    total_promo_redemptions = models.PositiveIntegerField(default=0)
    total_discount_given = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    flash_sale_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bundle_attach_rate = models.FloatField(default=0)
    coupon_redemption_rate = models.FloatField(default=0)
    spin_plays = models.PositiveIntegerField(default=0)
    scratch_plays = models.PositiveIntegerField(default=0)
    ad_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ad_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ad_roas = models.FloatField(default=0)
    email_open_rate = models.FloatField(default=0)
    email_click_rate = models.FloatField(default=0)
    push_open_rate = models.FloatField(default=0)
    sms_open_rate = models.FloatField(default=0)
    creator_gmv = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    abuse_signals_detected = models.PositiveIntegerField(default=0)
    by_promo_type = models.JSONField(default=dict, blank=True)
    by_channel = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────

class MarketingEvent(models.Model):
    """Append-only marketing-engine audit log. Every state transition
    in this app writes a row; ops uses it to debug "why did this user
    not get the X coupon?" weeks later."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='marketing_events',
        null=True, blank=True,
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='emitted_marketing_events',
    )
    kind = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'kind'])]

    @staticmethod
    def log(*, user=None, actor=None, kind, payload=None):
        try:
            return MarketingEvent.objects.create(
                user=user, actor=actor, kind=kind, payload=payload or {},
            )
        except Exception:
            return None
