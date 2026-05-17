"""
apps/gift_cards/models.py

Gift cards as a first-class ledger entity. Two tables:

  GiftCard            One card. Plaintext code shown ONCE at issue;
                      we store SHA-256(code) so a DB leak doesn't compromise
                      live cards. Initial value + current balance + currency
                      + status + expiry.

  GiftCardTransaction APPEND-ONLY ledger of every action on a card.
                      Kind ∈ {issue, redeem, refund, adjust, expire}.
                      balance_after snapshot lets us show "running balance"
                      timeline without re-summing.

Why a separate ledger table for gift cards instead of stuffing it into
the main ledger:
  • Gift cards have their own per-card identity that needs an inviolable
    audit trail ("show me the history of card #X"). Cross-account joins
    in the main ledger would be expensive.
  • Refunds against a gift-card-paid order need to ADD back to the card,
    not just refund cash. That's a per-card-balance operation, not a
    journal entry.
  • Compliance: regulators want to see the card-level chain of custody.

The main ledger still gets a journal entry for the AOA flow (cash in
on issue, cash out on redemption); GiftCardTransaction is the
card-specific receipt.
"""
import hashlib
import secrets
from decimal import Decimal
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class CardStatus(models.TextChoices):
    ACTIVE   = 'active',   'Active'
    REDEEMED = 'redeemed', 'Fully redeemed'
    EXPIRED  = 'expired',  'Expired'
    CANCELLED= 'cancelled','Cancelled by admin'


# Allowed characters in the user-typed portion of the code.
# No 0/O/1/I/L (ambiguous). Card format: GIFT-<4 chars>-<4 chars>-<4 chars>
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


class GiftCard(models.Model):
    """One physical or digital card. Code stored hashed."""
    # The full code is shown ONCE at issuance and never again. We keep
    # SHA-256(code) for verification + a 4-char user-visible prefix so
    # admins can identify a card in support tickets without seeing the
    # secret portion.
    code_hash = models.CharField(max_length=64, unique=True, db_index=True)
    code_prefix = models.CharField(max_length=4, db_index=True)
    initial_value = models.DecimalField(max_digits=12, decimal_places=2)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    status = models.CharField(
        max_length=10, choices=CardStatus.choices,
        default=CardStatus.ACTIVE, db_index=True,
    )

    # Who bought it (if known). NULL on admin-issued promo cards.
    purchased_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gift_cards_purchased',
    )
    # Who currently owns the card. Set at first claim — anyone with the
    # code can claim, but once claimed the binding is permanent (and
    # only the owner can redeem).
    claimed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gift_cards_owned',
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                       help_text='NULL = never expires')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['claimed_by', '-created_at']),
        ]

    # ── Code generation + hashing ──────────────────────────────────────
    @staticmethod
    def hash_code(plaintext: str) -> str:
        return hashlib.sha256(plaintext.upper().encode()).hexdigest()

    @staticmethod
    def generate_code() -> str:
        """GIFT-XXXX-XXXX-XXXX format, ambiguity-free alphabet."""
        parts = [
            ''.join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            for _ in range(3)
        ]
        return 'GIFT-' + '-'.join(parts)

    def __str__(self):
        return f'GiftCard({self.code_prefix}…, {self.current_balance} {self.currency}, {self.status})'


class GiftCardTransactionKind(models.TextChoices):
    ISSUE   = 'issue',   'Issued'
    CLAIM   = 'claim',   'Claimed by user'
    REDEEM  = 'redeem',  'Redeemed (debit)'
    REFUND  = 'refund',  'Refund (credit back)'
    ADJUST  = 'adjust',  'Admin adjustment'
    EXPIRE  = 'expire',  'Expired (balance forfeited)'
    CANCEL  = 'cancel',  'Cancelled by admin'


class GiftCardTransaction(models.Model):
    """Append-only per-card ledger row."""
    card = models.ForeignKey(GiftCard, on_delete=models.CASCADE,
                              related_name='transactions')
    kind = models.CharField(max_length=10, choices=GiftCardTransactionKind.choices,
                             db_index=True)
    # Signed: positive on issue/refund/adjust+, negative on redeem/expire/cancel.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)

    # Free-form ref back to the originating object (order id, refund id, etc.)
    ref_type = models.CharField(max_length=40, blank=True, db_index=True)
    ref_id = models.CharField(max_length=80, blank=True, db_index=True)

    # Idempotency: same (card, kind, ref) tuple can't produce two rows.
    # Protects against double-redemption from retried checkout calls.
    dedupe_key = models.CharField(max_length=120, blank=True, null=True,
                                    db_index=True)

    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['card', '-created_at']),
            models.Index(fields=['ref_type', 'ref_id']),
        ]
        constraints = [
            # NULL bypasses uniqueness (admin adjustments stack); same
            # non-NULL dedupe_key for same card collapses to one row.
            models.UniqueConstraint(
                fields=['card', 'dedupe_key'],
                name='uniq_card_dedupe_key',
            ),
        ]
        ordering = ['-created_at']
