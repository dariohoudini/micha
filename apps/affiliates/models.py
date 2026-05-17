"""
apps/affiliates/models.py

Affiliate / influencer commissions. Five tables:

  AffiliateProgram   The rules — default rate, attribution window, hold
                     period before payout, minimum payout. Operators can
                     run multiple programs (e.g. "Influencer" with 8%
                     vs "Friends & Family" with 3%).

  AffiliateAccount   One affiliate's profile within a program. Unique
                     code (short URL slug), tier multiplier, active flag,
                     bank for payout.

  AffiliateClick     Raw attribution event. Append-only. When a user
                     visits with ?ref=<code>, we create one row. The
                     cookie/session ties future order activity back to
                     this click via attribution lookup.

  AffiliateConversion  Materialised commission. One row per (order, affiliate).
                     status: pending → confirmed (past hold period) →
                     paid (settled to wallet/payout). REVERSED on refund
                     within hold window.

  AffiliatePayout    Aggregated payment to an affiliate covering N
                     confirmed conversions. Hooks into the existing
                     payout / wallet system.

The whole flow:

  Influencer shares link micha.ao/?ref=ALICE123
    → buyer clicks → AffiliateClick row + cookie
    → buyer purchases within attribution_window_days
    → AffiliateConversion row, status='pending', commission posted
       to ledger as PLATFORM_LIABILITY (we owe the affiliate)
    → After hold_period_days, beat task flips to 'confirmed'
       (clawback window has passed)
    → AffiliatePayout aggregates confirmed conversions → seller wallet
       or bank transfer
    → On refund within hold period → conversion REVERSED, ledger entry
       compensated, affiliate sees adjustment in next payout
"""
import secrets
from decimal import Decimal
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class AffiliateProgram(models.Model):
    """A named commission scheme. Operators can have multiple programs."""
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    # Default commission as a fraction (0.08 = 8%). Per-affiliate tier
    # multiplier on AffiliateAccount further adjusts this.
    default_commission_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal('0.0500'),
        help_text='0.05 = 5%',
    )
    # Days between click and order during which we still credit the click.
    attribution_window_days = models.PositiveSmallIntegerField(default=30)
    # Days a conversion stays 'pending' before flipping to 'confirmed'.
    # Long enough for refunds within the buyer-protection window to claw back.
    hold_period_days = models.PositiveSmallIntegerField(default=14)
    # Minimum payout — small accruals stay accumulated.
    min_payout_aoa = models.DecimalField(max_digits=12, decimal_places=2,
                                          default=Decimal('5000.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AffiliateAccount(models.Model):
    """An affiliate's profile within a program. One per (user, program)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='affiliate_accounts')
    program = models.ForeignKey(AffiliateProgram, on_delete=models.PROTECT,
                                  related_name='accounts')
    # Short, human-friendly slug used in URLs: micha.ao/?ref=ALICE123
    code = models.CharField(max_length=20, unique=True, db_index=True)
    # Per-affiliate multiplier on top of the program default. 1.0 = baseline.
    # Top influencers can be set to 1.5 = 50% bonus.
    tier_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('1.00'),
    )
    is_active = models.BooleanField(default=True)
    total_earned_aoa = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Sum of confirmed commissions (cached for fast reads).',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'program'],
                                    name='uniq_user_program'),
        ]

    @staticmethod
    def generate_code() -> str:
        """8-char URL-safe code. Excludes ambiguous chars (0/O/1/I)."""
        ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(secrets.choice(ALPHABET) for _ in range(8))

    def effective_rate(self) -> Decimal:
        return (self.program.default_commission_rate * self.tier_multiplier)


class AffiliateClick(models.Model):
    """A click on an affiliate link. Source for attribution lookup."""
    account = models.ForeignKey(AffiliateAccount, on_delete=models.CASCADE,
                                  related_name='clicks')
    # The user as known at click time (anon → NULL; resolved when they
    # log in within the session).
    user = models.ForeignKey(User, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='+')
    # Session-derived stable token for matching anonymous clicks → later
    # logged-in conversions.
    session_token = models.CharField(max_length=64, blank=True, db_index=True)
    # The product they landed on (if any), so we can credit context.
    landing_product_id = models.CharField(max_length=80, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    referrer = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['account', '-created_at']),
            models.Index(fields=['session_token', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]


class ConversionStatus(models.TextChoices):
    PENDING   = 'pending',   'Pending (within hold period)'
    CONFIRMED = 'confirmed', 'Confirmed (hold elapsed)'
    PAID      = 'paid',      'Paid out'
    REVERSED  = 'reversed',  'Reversed (refund)'
    REJECTED  = 'rejected',  'Rejected (fraud / policy)'


class AffiliateConversion(models.Model):
    """One commission row per attributed (order, affiliate)."""
    account = models.ForeignKey(AffiliateAccount, on_delete=models.CASCADE,
                                  related_name='conversions')
    # The originating click (always set — attribution must point at SOME click)
    click = models.ForeignKey(AffiliateClick, on_delete=models.PROTECT,
                                related_name='+')
    order_id = models.CharField(max_length=80, db_index=True)
    order_total = models.DecimalField(max_digits=14, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4)
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=ConversionStatus.choices,
        default=ConversionStatus.PENDING, db_index=True,
    )
    # When status moves out of PENDING
    confirmed_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_reason = models.CharField(max_length=200, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payout_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            # One conversion per (account, order). Multiple accounts could
            # in theory split-credit, but for now we credit the LAST click
            # before purchase (last-touch attribution).
            models.UniqueConstraint(fields=['account', 'order_id'],
                                    name='uniq_account_order'),
        ]
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['account', 'status', '-created_at']),
        ]


class AffiliatePayout(models.Model):
    """Aggregated payout covering N confirmed conversions."""
    account = models.ForeignKey(AffiliateAccount, on_delete=models.CASCADE,
                                  related_name='payouts')
    amount_aoa = models.DecimalField(max_digits=14, decimal_places=2)
    conversion_count = models.PositiveIntegerField()
    status = models.CharField(
        max_length=12,
        choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')],
        default='pending', db_index=True,
    )
    # Reference into the external payout system (bank transaction id, etc.)
    external_ref = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
