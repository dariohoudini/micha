"""
Buyer Acquisition & Retention models
=====================================

Implements AliExpress_Buyer_Acquisition_Retention.docx CH1–CH24 at
the DB layer. We deliberately don't re-create things already
modelled elsewhere:

  - Loyalty tiers / points / coins → apps.loyalty
  - Referral rewards → apps.users.ReferralReward + apps.affiliates
  - Cart abandonment ping flag → apps.cart.Cart.last_abandonment_ping_at
  - Back-in-stock / price-drop alerts → apps.recommendations + apps.ai_engine
  - Push notifications → apps.notifications
  - Coupons / flash sales → apps.promotions

New tables in this app cover the parts NOT yet shipped:

  CH1     AcquisitionChannelSpend           — paid-media spend ledger
  CH2     BuyerAttributionTouch                  — UTM → install → first purchase chain
  CH3     WelcomeIncentive                  — new-user coupon/credit grant
  CH4     FirstPurchaseTrigger              — fired after first net-positive order
  CH5     ReferralActivation                — referral link click → conversion
  CH10    PremiumMembership + MembershipBillingLog
  CH11/12 RecoverySequenceState             — cart + checkout state machine
  CH13    BrowseAbandonmentSignal           — session-end signal for retargeting
  CH16    DormancyState + WinBackCampaignRun
  CH17    PushDecision                      — per-notification decision log
  CH18    EmailLifecycleLog                 — buyer-side lifecycle audit
  CH19    HomeFeedPersonalisation           — block-selection snapshot
  CH20    BirthdayReward
  CH21    SeasonalCampaign + SeasonalCampaignParticipant
  CH22    SocialShareEvent + ViralLoopAttribution
  CH23    BuyerLTV                          — predicted + realised
  CH24    BuyerKpiSnapshot                  — daily acquisition + retention KPIs
  Audit   EngagementEvent                   — append-only per-buyer audit trail

Every state change writes an EngagementEvent row.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ── CH1 — Acquisition channels & spend ───────────────────────────

ACQ_CHANNEL_CHOICES = (
    ('organic_web',     'Organic — Web'),
    ('organic_search',  'Organic — Search'),
    ('paid_search',     'Paid Search (Google/Bing)'),
    ('paid_social',     'Paid Social (Meta/TikTok)'),
    ('display',         'Display network'),
    ('influencer',      'Influencer / Affiliate'),
    ('referral',        'Referral programme'),
    ('email',           'Email — owned'),
    ('push',            'Push — owned'),
    ('partner',         'Partner — coreg'),
    ('offline',         'Offline / OOH'),
    ('app_store',       'App store browse'),
)


class AcquisitionChannelSpend(models.Model):
    """Daily spend + acquired-user counts per (date, channel, market).
    Driven by the MMP feed in production; for now we accept manual
    inserts so the KPI dashboard has something to read."""

    id = models.BigAutoField(primary_key=True)
    snapshot_date = models.DateField(db_index=True)
    channel = models.CharField(max_length=24, choices=ACQ_CHANNEL_CHOICES)
    country = models.CharField(max_length=2)
    spend_usd = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    installs = models.PositiveIntegerField(default=0)
    registrations = models.PositiveIntegerField(default=0)
    first_purchases = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('snapshot_date', 'channel', 'country')]
        indexes = [models.Index(fields=['snapshot_date', 'channel'])]


# ── CH2 — Attribution chain ──────────────────────────────────────

ATTRIBUTION_STAGE_CHOICES = (
    ('first_touch',     'First touch (impression/click)'),
    ('install',         'App install / first session'),
    ('registration',    'Registration / account creation'),
    ('first_purchase',  'First purchase'),
)


class BuyerAttributionTouch(models.Model):
    """One row per attribution event in the user's funnel. The
    `attribution_id` is shared across rows that belong to the same
    user-journey (cookie/AAID/IDFA) so a join answers
    "what was the first-touch channel for this customer?"."""

    id = models.BigAutoField(primary_key=True)
    attribution_id = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='buyer_attribution_touches',
    )
    stage = models.CharField(max_length=24, choices=ATTRIBUTION_STAGE_CHOICES)
    channel = models.CharField(max_length=24, choices=ACQ_CHANNEL_CHOICES, blank=True, default='')
    utm_source = models.CharField(max_length=120, blank=True, default='')
    utm_medium = models.CharField(max_length=120, blank=True, default='')
    utm_campaign = models.CharField(max_length=120, blank=True, default='')
    utm_term = models.CharField(max_length=120, blank=True, default='')
    utm_content = models.CharField(max_length=120, blank=True, default='')
    referrer = models.CharField(max_length=255, blank=True, default='')
    landing_path = models.CharField(max_length=255, blank=True, default='')
    device_type = models.CharField(max_length=16, blank=True, default='')
    country = models.CharField(max_length=2, blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['occurred_at']
        indexes = [
            models.Index(fields=['attribution_id', 'stage']),
            models.Index(fields=['user', 'stage']),
        ]


# ── CH3 — Welcome incentive ──────────────────────────────────────

WELCOME_TYPE_CHOICES = (
    ('coupon',  'Coupon code'),
    ('credit',  'Wallet credit'),
    ('coins',   'Coins grant'),
)

WELCOME_STATUS_CHOICES = (
    ('issued',    'Issued'),
    ('used',      'Used on first purchase'),
    ('expired',   'Expired'),
    ('voided',    'Voided (anti-abuse)'),
)


class WelcomeIncentive(models.Model):
    """CH3 — record of the welcome offer granted to a new user. We
    persist the grant explicitly (not just on the underlying Coupon)
    so the funnel and abuse-detection queries are cheap."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='welcome_incentives')
    incentive_type = models.CharField(max_length=12, choices=WELCOME_TYPE_CHOICES)
    coupon_code = models.CharField(max_length=40, blank=True, default='')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    minimum_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    issued_via_channel = models.CharField(max_length=24, blank=True, default='')
    status = models.CharField(max_length=12, choices=WELCOME_STATUS_CHOICES, default='issued')
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_on_order_id = models.CharField(max_length=64, blank=True, default='')
    voided_reason = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status'])]


# ── CH4 — First purchase trigger ─────────────────────────────────

class FirstPurchaseTrigger(models.Model):
    """CH4.1 — single-row-per-user record proving the user has placed
    their first net-positive order. Refunds → status='reverted' so a
    fraudulent first-purchase-then-refund pattern can't farm rewards."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='first_purchase_trigger')
    order_id = models.CharField(max_length=64)
    purchased_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    rewards_released = models.JSONField(default=list, blank=True)
    referrer_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='referred_first_purchases',
    )
    status = models.CharField(
        max_length=16, default='pending',
        choices=(('pending', 'Pending verify'), ('verified', 'Verified'),
                 ('reverted', 'Reverted (refund/chargeback)')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ── CH5 — Referral activation chain ──────────────────────────────

REFERRAL_STAGE_CHOICES = (
    ('link_click',    'Link click'),
    ('install',       'Install'),
    ('registration',  'Registration'),
    ('first_purchase','First purchase'),
    ('rewarded',      'Reward issued'),
)


class ReferralActivation(models.Model):
    """CH5.2 — each touch in the referral chain. Joined on
    referee_user once they register."""

    id = models.BigAutoField(primary_key=True)
    referrer_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='referral_activations_sent',
    )
    referral_code = models.CharField(max_length=40, db_index=True)
    referee_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='referral_activations_received',
    )
    stage = models.CharField(max_length=24, choices=REFERRAL_STAGE_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=64, blank=True, default='')
    fraud_score = models.PositiveSmallIntegerField(default=0)
    occurred_at = models.DateTimeField(auto_now_add=True)


# ── CH10 — Premium membership ────────────────────────────────────

MEMBERSHIP_PLAN_CHOICES = (
    ('monthly',  'Monthly'),
    ('quarterly','Quarterly'),
    ('annual',   'Annual'),
)

MEMBERSHIP_STATUS_CHOICES = (
    ('trial',         'Trial period'),
    ('active',        'Active — paid'),
    ('grace',         'Grace — payment failed, retry'),
    ('cancelled',     'Cancelled — not renewing'),
    ('expired',       'Expired'),
    ('suspended',     'Suspended (chargeback / abuse)'),
)


class PremiumMembership(models.Model):
    """CH10. One row per user (one-to-one). Subscription is the
    "MICHA Plus" tier — flat monthly fee, perks include free shipping,
    fast refund, double coins, exclusive flash sales."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='premium_membership')
    plan = models.CharField(max_length=12, choices=MEMBERSHIP_PLAN_CHOICES, default='monthly')
    status = models.CharField(max_length=12, choices=MEMBERSHIP_STATUS_CHOICES, default='trial')
    started_at = models.DateTimeField(auto_now_add=True)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=80, blank=True, default='')
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    failed_charge_count = models.PositiveSmallIntegerField(default=0)
    last_charged_at = models.DateTimeField(null=True, blank=True)


class MembershipBillingLog(models.Model):
    """One row per attempted charge. Status `succeeded` advances
    the period; `failed` increments failed_charge_count → `grace` →
    after 3 fails → `expired`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(
        PremiumMembership, on_delete=models.CASCADE, related_name='billing_logs',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    psp_reference = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(
        max_length=16,
        choices=(('succeeded', 'Succeeded'), ('failed', 'Failed'),
                 ('refunded', 'Refunded')),
    )
    failure_code = models.CharField(max_length=40, blank=True, default='')
    attempted_at = models.DateTimeField(auto_now_add=True)


# ── CH11 / CH12 — Recovery sequence ──────────────────────────────

RECOVERY_KIND_CHOICES = (
    ('cart',      'Cart abandonment'),
    ('checkout',  'Checkout abandonment'),
    ('browse',    'Browse abandonment'),
)

RECOVERY_STATUS_CHOICES = (
    ('active',     'Active — still in sequence'),
    ('converted',  'Converted — purchase completed'),
    ('completed',  'Completed — sequence finished'),
    ('opted_out',  'User opted out'),
)


class RecoverySequenceState(models.Model):
    """CH11.3. One row per (user, kind, started_at) so a user who
    abandons twice in the same day gets two parallel sequences
    (the doc spec). `current_step` walks 0..N; `next_message_at`
    is when the worker should fire the next step."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recovery_sequences')
    kind = models.CharField(max_length=12, choices=RECOVERY_KIND_CHOICES, db_index=True)
    target_id = models.CharField(max_length=64, blank=True, default='')   # cart_id / product_id
    target_payload = models.JSONField(default=dict, blank=True)
    current_step = models.PositiveSmallIntegerField(default=0)
    total_steps = models.PositiveSmallIntegerField(default=5)
    next_message_at = models.DateTimeField()
    last_message_sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=RECOVERY_STATUS_CHOICES, default='active',
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['next_message_at']
        indexes = [
            models.Index(fields=['status', 'next_message_at']),
            models.Index(fields=['user', 'kind']),
        ]


# ── CH13 — Browse abandonment signal ─────────────────────────────

class BrowseAbandonmentSignal(models.Model):
    """CH13.1. Captured at session end when the user looked at >=3
    products of the same category but didn't add anything to cart.
    Drives the remarketing message decision."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='browse_signals')
    session_id = models.CharField(max_length=64, blank=True, default='')
    products_viewed_ids = models.JSONField(default=list, blank=True)
    primary_category_id = models.CharField(max_length=64, blank=True, default='')
    avg_view_duration_sec = models.PositiveIntegerField(default=0)
    high_intent = models.BooleanField(default=False)
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'notified', '-created_at'])]


# ── CH16 — Win-back / dormancy ───────────────────────────────────

DORMANCY_BAND_CHOICES = (
    ('active',          'Active — purchased ≤30 days'),
    ('lapsing',         'Lapsing — 31-60 days'),
    ('dormant_30',      'Dormant 30-60d'),
    ('dormant_60',      'Dormant 60-90d'),
    ('dormant_90',      'Dormant 90-180d'),
    ('dormant_180',     'Dormant 180-365d'),
    ('dormant_365_plus','Dormant 365+d — likely churned'),
)

WINBACK_OUTCOME_CHOICES = (
    ('sent',         'Sent'),
    ('opened',       'Opened'),
    ('clicked',      'Clicked'),
    ('reactivated',  'Reactivated (made purchase)'),
    ('opted_out',    'Opted out'),
    ('expired',      'Expired without action'),
)


class DormancyState(models.Model):
    """CH16.1. Single source of truth for "where in the dormancy
    funnel is this user right now?". Recomputed nightly by the
    dormancy worker; campaigns key off this row."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dormancy_state')
    band = models.CharField(max_length=20, choices=DORMANCY_BAND_CHOICES, default='active')
    last_purchase_at = models.DateTimeField(null=True, blank=True)
    days_since_last_purchase = models.PositiveIntegerField(default=0)
    last_session_at = models.DateTimeField(null=True, blank=True)
    days_since_last_session = models.PositiveIntegerField(default=0)
    lifetime_orders = models.PositiveIntegerField(default=0)
    lifetime_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)


class WinBackCampaignRun(models.Model):
    """Per-user, per-band campaign send. Idempotent on
    (user, band, sent_at_date) — we don't double-hit the same user in
    the same band on the same day."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='winback_runs')
    band = models.CharField(max_length=20, choices=DORMANCY_BAND_CHOICES)
    template_key = models.CharField(max_length=64)
    incentive_kind = models.CharField(max_length=16, blank=True, default='')
    incentive_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    channels_used = models.JSONField(default=list, blank=True)  # ["email", "push"]
    outcome = models.CharField(max_length=16, choices=WINBACK_OUTCOME_CHOICES, default='sent')
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    reactivated_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)


# ── CH17 — Push decision log ─────────────────────────────────────

class PushDecision(models.Model):
    """Every push notification we attempt (or skip) for a user lands
    here, with the reason. Lets ops answer "why didn't user X get the
    Black Friday push?" without spelunking."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_decisions')
    push_type = models.CharField(max_length=40)
    decision = models.CharField(
        max_length=20,
        choices=(('sent', 'Sent'), ('suppressed', 'Suppressed'),
                 ('failed', 'Failed'), ('throttled', 'Throttled')),
    )
    reason = models.CharField(max_length=80, blank=True, default='')
    segment_id = models.CharField(max_length=64, blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ── CH18 — Email lifecycle log (buyer side) ──────────────────────

EMAIL_LIFECYCLE_STAGE_CHOICES = (
    ('welcome',          'Welcome'),
    ('post_register',    'Post-registration'),
    ('first_purchase',   'First purchase'),
    ('order_confirm',    'Order confirmation'),
    ('post_purchase',    'Post-purchase'),
    ('review_request',   'Review request'),
    ('cart_recovery',    'Cart recovery'),
    ('checkout_recovery','Checkout recovery'),
    ('back_in_stock',    'Back-in-stock'),
    ('price_drop',       'Price drop'),
    ('birthday',         'Birthday'),
    ('win_back',         'Win-back'),
    ('membership_renew', 'Membership renewal'),
    ('flash_sale',       'Flash sale'),
)


class EmailLifecycleLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_lifecycle_logs')
    stage = models.CharField(max_length=24, choices=EMAIL_LIFECYCLE_STAGE_CHOICES, db_index=True)
    template_key = models.CharField(max_length=64)
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16, default='queued',
        choices=(('queued', 'Queued'), ('sent', 'Sent'),
                 ('opened', 'Opened'), ('clicked', 'Clicked'),
                 ('failed', 'Failed'), ('suppressed', 'Suppressed')),
    )
    suppression_reason = models.CharField(max_length=80, blank=True, default='')
    queued_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)


# ── CH19 — Personalisation snapshot ──────────────────────────────

class HomeFeedPersonalisation(models.Model):
    """Per-(user, snapshot) selection of feed blocks. The
    recommendations app supplies the affinity vector; this row
    records the *decision* the personaliser made so we can replay it
    for debugging."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='home_feed_snapshots')
    affinity_vector = models.JSONField(default=dict, blank=True)
    blocks_selected = models.JSONField(default=list, blank=True)
    blocks_demoted = models.JSONField(default=list, blank=True)
    experiment_id = models.CharField(max_length=40, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)


# ── CH20 — Birthday reward ───────────────────────────────────────

class BirthdayReward(models.Model):
    """One row per (user, birthday-year). Idempotent so a re-run of
    the daily worker can't double-grant."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='birthday_rewards')
    birthday_year = models.PositiveSmallIntegerField()
    coupon_code = models.CharField(max_length=40, blank=True, default='')
    coins_granted = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('user', 'birthday_year')]


# ── CH21 — Seasonal campaign ─────────────────────────────────────

CAMPAIGN_STATUS_CHOICES = (
    ('draft',     'Draft'),
    ('scheduled', 'Scheduled'),
    ('live',      'Live'),
    ('finished',  'Finished'),
    ('cancelled', 'Cancelled'),
)


class SeasonalCampaign(models.Model):
    """11.11, Black Friday, etc. The product catalogue selection,
    promo tile, and search-rank boost configs are stored as JSON for
    the personaliser to apply at render time."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    country_scope = models.JSONField(default=list, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=CAMPAIGN_STATUS_CHOICES, default='draft')
    discount_pct = models.PositiveSmallIntegerField(default=0)
    banner_key = models.CharField(max_length=255, blank=True, default='')
    boost_multiplier = models.FloatField(default=1.0)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SeasonalCampaignParticipant(models.Model):
    """Per-user opt-in or auto-enrolment for a seasonal campaign,
    plus the rewards they accumulated."""

    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(SeasonalCampaign, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seasonal_participations')
    auto_enrolled = models.BooleanField(default=True)
    orders_during_campaign = models.PositiveIntegerField(default=0)
    gmv_during_campaign = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus_coins_awarded = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('campaign', 'user')]


# ── CH22 — Social share virality ─────────────────────────────────

SHARE_TARGET_CHOICES = (
    ('whatsapp',   'WhatsApp'),
    ('facebook',   'Facebook'),
    ('instagram',  'Instagram'),
    ('twitter',    'Twitter / X'),
    ('telegram',   'Telegram'),
    ('email',      'Email'),
    ('sms',        'SMS'),
    ('copy_link',  'Copy link'),
    ('other',      'Other'),
)

SHARED_ENTITY_CHOICES = (
    ('product',    'Product'),
    ('store',      'Seller store'),
    ('flash_sale', 'Flash sale'),
    ('coupon',     'Coupon'),
    ('referral',   'Referral link'),
)


class SocialShareEvent(models.Model):
    """CH22.1. Every share intent fires a row here so we can compute
    the K-factor (downstream clicks/installs per share)."""

    id = models.BigAutoField(primary_key=True)
    sharer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='shares_sent')
    share_target = models.CharField(max_length=16, choices=SHARE_TARGET_CHOICES)
    shared_entity = models.CharField(max_length=16, choices=SHARED_ENTITY_CHOICES)
    entity_id = models.CharField(max_length=64)
    short_code = models.CharField(max_length=20, unique=True, db_index=True)
    clicks = models.PositiveIntegerField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def make_short_code():
        return secrets.token_urlsafe(9)[:12]


class ViralLoopAttribution(models.Model):
    """When a downstream user converts via a share link, we record the
    edge here. Joining over both tables yields the viral graph."""

    id = models.BigAutoField(primary_key=True)
    share_event = models.ForeignKey(SocialShareEvent, on_delete=models.CASCADE, related_name='attributions')
    converted_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='viral_attributions_received',
    )
    conversion_kind = models.CharField(max_length=24)  # install / register / purchase
    occurred_at = models.DateTimeField(auto_now_add=True)


# ── CH23 — LTV ───────────────────────────────────────────────────

class BuyerLTV(models.Model):
    """CH23. Realised (90/180/365/lifetime) + predicted next-12-month
    LTV. Recomputed nightly for the active buyer base."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ltv')
    realised_90d = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    realised_180d = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    realised_365d = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    realised_lifetime = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    predicted_next_12m = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    confidence = models.FloatField(default=0.0)
    segment = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Low / Mid / High / VIP — bucket for activation campaigns',
    )
    rfm_recency = models.PositiveSmallIntegerField(default=0)
    rfm_frequency = models.PositiveSmallIntegerField(default=0)
    rfm_monetary = models.PositiveSmallIntegerField(default=0)
    last_computed_at = models.DateTimeField(auto_now=True)


# ── CH24 — Buyer KPI snapshot ────────────────────────────────────

class BuyerKpiSnapshot(models.Model):
    """Daily roll-up of buyer acquisition + retention KPIs from CH24.
    Recomputed by the snapshot Celery task."""

    snapshot_date = models.DateField(primary_key=True)
    new_users = models.PositiveIntegerField(default=0)
    new_buyers = models.PositiveIntegerField(default=0)
    blended_cac = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_cac = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    first_purchase_within_7d_pct = models.FloatField(default=0)
    first_purchase_within_30d_pct = models.FloatField(default=0)
    activation_rate = models.FloatField(default=0)  # registrations → first_purchase
    d7_retention_pct = models.FloatField(default=0)
    d30_retention_pct = models.FloatField(default=0)
    d90_retention_pct = models.FloatField(default=0)
    avg_orders_per_buyer = models.FloatField(default=0)
    avg_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    repeat_buyer_rate = models.FloatField(default=0)
    churn_30d_pct = models.FloatField(default=0)
    dormant_population = models.PositiveIntegerField(default=0)
    by_channel = models.JSONField(default=dict, blank=True)
    by_country = models.JSONField(default=dict, blank=True)
    by_segment = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Template catalogue (push + email)
# ─────────────────────────────────────────────────────────────────

TEMPLATE_KIND_CHOICES = (
    ('push',  'Push notification'),
    ('email', 'Email'),
    ('inapp', 'In-app banner'),
)


class MessageTemplate(models.Model):
    """One row per (key, locale, kind). The lifecycle worker selects
    a template by `key` + the user's `locale` and renders it with
    Python str.format() substitution against the supplied context.

    Keeping templates in the DB rather than in code means ops /
    growth can A/B subject lines without a deploy. The `is_active`
    flag lets the team pause a template instantly during an
    incident."""

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=8, choices=TEMPLATE_KIND_CHOICES, default='email')
    locale = models.CharField(max_length=10, default='pt-AO')
    subject = models.CharField(max_length=255, blank=True, default='')
    body = models.TextField()
    deep_link = models.CharField(max_length=255, blank=True, default='')
    cta_label = models.CharField(max_length=80, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('key', 'kind', 'locale')]
        ordering = ['key', 'kind', 'locale']


# ── Audit log ────────────────────────────────────────────────────

class EngagementEvent(models.Model):
    """Per-buyer audit row. Every welcome incentive issue, recovery
    sequence transition, membership state change, win-back send, etc.
    writes one row so support / analytics can answer the timeline
    question without re-stitching tables."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='engagement_events',
        null=True, blank=True,
    )
    kind = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'kind'])]

    @staticmethod
    def log(*, user=None, kind, payload=None):
        try:
            return EngagementEvent.objects.create(
                user=user, kind=kind, payload=payload or {},
            )
        except Exception:
            return None
