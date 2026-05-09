"""
Double-entry ledger for MICHA.

Design principles
-----------------
* Every money movement is at least TWO LedgerEntry rows: one debit, one credit.
* Sum of (credits − debits) across all accounts must equal zero at all times.
* Balances are *derived* (`Σ credits − Σ debits` over an account) — never mutated.
* Posting is atomic and idempotent (via `idempotency_key` on the journal).
* All amounts are integer Kwanza centavos (1 Kz = 100 cents) to dodge float / rounding bugs.
* `Account` rows are typed by `AccountType` so we can prove invariants per category
  (e.g. "platform liability accounts always have credit balance").

Why a separate `Journal`?
-------------------------
A journal is a logical grouping of entries that must succeed together (debit X +
credit Y for one transfer, or debit X + credit Y + credit Z for a transfer with
a fee). The journal is the unit of idempotency.
"""
from decimal import Decimal
from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum, Q


User = settings.AUTH_USER_MODEL


class AccountType(models.TextChoices):
    # User-owned accounts ("liability" from platform's POV — money owed to users)
    USER_STORE_CREDIT = 'user_store_credit', 'User · Store credit (loyalty Kz)'
    USER_LOYALTY_POINTS = 'user_loyalty_points', 'User · Loyalty points'
    SELLER_WALLET = 'seller_wallet', 'Seller · Wallet (payout-eligible)'
    SELLER_PENDING = 'seller_pending', 'Seller · Pending (in escrow)'

    # Platform-owned accounts ("equity / revenue / liability")
    PLATFORM_REVENUE = 'platform_revenue', 'Platform · Revenue (commission)'
    PLATFORM_LOYALTY_FUND = 'platform_loyalty_fund', 'Platform · Loyalty fund (counter for credits awarded to users)'
    PLATFORM_REFUND_POOL = 'platform_refund_pool', 'Platform · Refund pool'
    PLATFORM_FEE_GATEWAY = 'platform_fee_gateway', 'Platform · Gateway fees collected'

    # Buyer side (payments received)
    BUYER_PAYMENTS = 'buyer_payments', 'Buyer · Payments received (clearing)'

    # External clearing (buyer's external payment funded into the system)
    EXTERNAL_CLEARING = 'external_clearing', 'External clearing (payment gateway)'


class LedgerError(Exception):
    """Raised when a ledger operation cannot complete safely."""


class Account(models.Model):
    """One row per balance-bearing entity.

    Per-user accounts (store_credit / loyalty_points) are auto-created via
    a signal on User creation. Singleton platform accounts are created on
    demand by `Account.platform(account_type)`.
    """
    type = models.CharField(max_length=40, choices=AccountType.choices, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='ledger_accounts',
        help_text='Null for platform / singleton accounts',
    )
    currency = models.CharField(max_length=3, default='AOA')
    name = models.CharField(max_length=120, blank=True, help_text='Optional human-readable label')
    is_active = models.BooleanField(default=True)

    # Cached balance (derived from entries). Never trust this for writes —
    # always recompute when applying logic. Useful for fast list queries.
    cached_balance_cents = models.BigIntegerField(default=0)
    cached_balance_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Per-user account: unique per (type, user)
            models.UniqueConstraint(
                fields=['type', 'user'],
                condition=Q(user__isnull=False),
                name='ledger_account_unique_per_user_type',
            ),
            # Platform account: only one per type
            models.UniqueConstraint(
                fields=['type'],
                condition=Q(user__isnull=True),
                name='ledger_account_singleton_platform_type',
            ),
        ]
        indexes = [
            models.Index(fields=['type', 'user']),
        ]

    def __str__(self):
        if self.user_id:
            return f'{self.get_type_display()} · {self.user_id}'
        return self.get_type_display()

    @classmethod
    def platform(cls, account_type, currency='AOA'):
        """Get-or-create the singleton platform account for this type."""
        obj, _ = cls.objects.get_or_create(
            type=account_type, user=None,
            defaults={'currency': currency},
        )
        return obj

    @classmethod
    def for_user(cls, user, account_type, currency='AOA'):
        obj, _ = cls.objects.get_or_create(
            type=account_type, user=user,
            defaults={'currency': currency},
        )
        return obj

    def balance(self):
        """Live balance in cents. Trust this; ignore cached_balance_cents for writes."""
        result = self.entries.aggregate(
            credit_sum=Sum('credit_cents'),
            debit_sum=Sum('debit_cents'),
        )
        return (result['credit_sum'] or 0) - (result['debit_sum'] or 0)

    def balance_decimal(self):
        return Decimal(self.balance()) / Decimal(100)


class Journal(models.Model):
    """A group of LedgerEntry rows that must apply together.

    Idempotency: posting with the same `idempotency_key` is a no-op (returns
    the existing journal). Use `f"{ref_type}:{ref_id}:{purpose}"` as the key,
    e.g. "order:abc-uuid:cashback".
    """
    idempotency_key = models.CharField(max_length=200, unique=True, db_index=True)
    description = models.CharField(max_length=300, blank=True)
    ref_type = models.CharField(max_length=40, blank=True, db_index=True,
                                help_text='e.g. "order", "checkin", "refund"')
    ref_id = models.CharField(max_length=80, blank=True, db_index=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['ref_type', 'ref_id', '-created_at'])]
        ordering = ['-created_at']


class LedgerEntry(models.Model):
    """One half of a balanced posting.

    Exactly one of (debit_cents, credit_cents) is > 0 on each row.
    Currency is on the account; we don't mix currencies in one journal.
    """
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='entries')
    debit_cents = models.BigIntegerField(default=0)
    credit_cents = models.BigIntegerField(default=0)
    description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Exactly one direction non-zero, both non-negative
            models.CheckConstraint(
                condition=(
                    Q(debit_cents__gte=0) & Q(credit_cents__gte=0)
                    & ~Q(debit_cents=0, credit_cents=0)
                    & (Q(debit_cents=0) | Q(credit_cents=0))
                ),
                name='ledger_entry_exactly_one_direction',
            ),
        ]
        indexes = [
            models.Index(fields=['account', '-created_at']),
        ]

    def __str__(self):
        side = f'+{self.credit_cents}' if self.credit_cents else f'-{self.debit_cents}'
        return f'{self.account} {side} ({self.description})'
