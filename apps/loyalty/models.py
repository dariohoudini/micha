"""
apps/loyalty/models.py

Loyalty system. Four tables:

  Tier               Bronze / Silver / Gold / Platinum (configurable). Defines
                     the qualifying spend threshold in a rolling window AND
                     points-multiplier for new earnings (Gold buyers earn 1.5×).

  TierBenefit        Per-tier perks: shipping_discount_pct, free_returns,
                     early_access_hours, priority_support, custom JSON.

  UserTier           Cached "current tier" per user. Recomputed by a beat
                     task from the qualifying-spend rolling window — reads
                     are O(1) at request time.

  PointsTransaction  APPEND-ONLY ledger. The legacy User.loyalty_points
                     counter becomes a cached projection; this table is the
                     source of truth. Every earn / redeem / adjustment /
                     expiry is one row.

Why a ledger + cached counter:
  Same reason FX has temporal rates: a counter alone can't answer "show me
  the points that were earned from order X and later redeemed against
  order Y". Auditors, customer support, fraud investigators all need that
  receipt. The counter on User stays for cheap reads.
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class TierCode(models.TextChoices):
    BRONZE   = 'BRONZE',   'Bronze'
    SILVER   = 'SILVER',   'Silver'
    GOLD     = 'GOLD',     'Gold'
    PLATINUM = 'PLATINUM', 'Platinum'


class Tier(models.Model):
    """The set of available tiers. Editable so the platform team can shift
    thresholds for a market without code deploys."""
    code = models.CharField(max_length=10, choices=TierCode.choices, unique=True)
    rank = models.PositiveSmallIntegerField(unique=True,
                                            help_text='Higher = better. Bronze=1, Platinum=4.')
    name = models.CharField(max_length=40)
    # Qualifying-spend threshold in AOA over the rolling window
    # (default window = 365 days; tunable in TierConfig).
    spend_threshold = models.DecimalField(max_digits=12, decimal_places=2,
                                          help_text='AOA total in qualifying window')
    # New-points-earned multiplier. 1.0 = base; Gold=1.5 etc.
    points_multiplier = models.DecimalField(max_digits=4, decimal_places=2,
                                            default=1.0)
    color = models.CharField(max_length=20, blank=True)
    icon = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['rank']

    def __str__(self):
        return f'{self.name} (rank {self.rank})'


class TierBenefit(models.Model):
    """One row per benefit a tier confers. Multiple rows per tier allowed
    so the perk list can grow without schema changes."""
    BENEFIT_KINDS = [
        ('shipping_discount', 'Shipping discount %'),
        ('cashback_pct',      'Cashback %'),
        ('free_returns',      'Free returns'),
        ('priority_support',  'Priority support queue'),
        ('early_access_hours','Early access (h) to sales'),
        ('birthday_bonus',    'Birthday bonus points'),
        ('extended_protection','Extended buyer protection (days)'),
    ]
    tier = models.ForeignKey(Tier, on_delete=models.CASCADE, related_name='benefits')
    kind = models.CharField(max_length=24, choices=BENEFIT_KINDS)
    # value interpretation depends on kind: pct (0-100), bool 1/0, hours, days, etc.
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tier', 'kind'], name='uniq_tier_benefit_kind'),
        ]


class UserTier(models.Model):
    """Cached current tier per user. The beat task ``loyalty.recompute_tiers``
    refreshes this from the rolling spend window. Reads at request time are
    O(1) via the OneToOne FK on User."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='loyalty_tier')
    tier = models.ForeignKey(Tier, on_delete=models.PROTECT, related_name='users')
    qualifying_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                            help_text='AOA spent in last 365 days')
    # When the user reached this tier (used for "downgrade grace" — we don't
    # demote immediately when spend drops; give them N days at the higher tier).
    achieved_at = models.DateTimeField(auto_now_add=True)
    last_recomputed_at = models.DateTimeField(auto_now=True)


class PointsReason(models.TextChoices):
    EARN_ORDER       = 'earn_order',       'Earned from order'
    EARN_REVIEW      = 'earn_review',      'Earned from review'
    EARN_REFERRAL    = 'earn_referral',    'Earned from referral'
    EARN_BIRTHDAY    = 'earn_birthday',    'Birthday bonus'
    REDEEM_DISCOUNT  = 'redeem_discount',  'Redeemed for discount'
    REDEEM_CREDIT    = 'redeem_credit',    'Redeemed for store credit'
    ADJUST_ADMIN     = 'adjust_admin',     'Admin adjustment'
    EXPIRE           = 'expire',           'Points expired'
    REVERSAL         = 'reversal',         'Reversed (refund/dispute)'


class PointsTransaction(models.Model):
    """Append-only points ledger. Source of truth — User.loyalty_points is
    a cached projection of SUM(delta) for the user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='points_transactions')
    # Positive = earned; negative = spent/expired/reversed.
    delta = models.IntegerField()
    reason = models.CharField(max_length=20, choices=PointsReason.choices, db_index=True)

    # Free-form ref back to the originating object
    ref_type = models.CharField(max_length=40, blank=True, db_index=True)
    ref_id   = models.CharField(max_length=80, blank=True, db_index=True)

    # Snapshot of the user's balance AFTER this transaction. Lets us show
    # the user a "running balance" timeline without re-summing per row.
    balance_after = models.IntegerField()

    # Idempotency: a single (user, reason, ref) tuple must produce at most
    # one earn-row — protects against double-credit if order webhook fires
    # twice. NULL bypasses uniqueness (admin adjustments may stack).
    # NULL chosen over '' because SQLite's partial-constraint support is
    # weaker than Postgres'; NULL is universally treated as "absent" by SQL.
    dedupe_key = models.CharField(max_length=120, blank=True, null=True, db_index=True)

    note = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['ref_type', 'ref_id']),
        ]
        constraints = [
            # Same dedupe_key (e.g. "order:<id>:earn") can't produce two rows.
            # NULL dedupe bypasses (admin adjustments don't dedupe).
            models.UniqueConstraint(
                fields=['user', 'dedupe_key'],
                name='uniq_user_points_dedupe',
            ),
        ]
        ordering = ['-created_at']
