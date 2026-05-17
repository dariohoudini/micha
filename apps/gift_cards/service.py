"""
apps/gift_cards/service.py

Public entrypoints:

  issue(amount, currency='AOA', purchased_by=None, expires_at=None,
        actor=None) -> (card, plaintext_code)
    Mint a new card. PLAINTEXT IS RETURNED ONCE — caller passes it to
    the buyer (email / print / SMS). Never recoverable after this call.

  claim(plaintext_code, user) -> GiftCard
    Bind a card to a user. Once claimed, only that user can redeem.
    Refused on already-claimed cards (we don't transfer ownership — the
    bearer-instrument model would be UX-friendly but easier to abuse).

  redeem(card, amount, *, ref_type, ref_id, actor=None) -> GiftCardTransaction
    Atomic debit. Refuses if insufficient balance or card not ACTIVE.
    Idempotent per (card, ref_type, ref_id) — same redemption from a
    retried checkout returns the existing row.

  refund_redemption(card, amount, *, original_ref_type, original_ref_id,
                    actor=None) -> GiftCardTransaction
    Credit back to a card when an order paid with it is refunded.
    Linked via ref to the original redemption.

  expire_cards() — beat task. Cards past expires_at with positive balance
    get a final EXPIRE transaction that zeros them out.

All mutating ops go through transaction.atomic() + SELECT FOR UPDATE on
the card row so concurrent redeem/refund cannot race past the balance
check.
"""
from __future__ import annotations
import logging
from decimal import Decimal
from datetime import datetime

from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import (
    GiftCard, GiftCardTransaction, GiftCardTransactionKind, CardStatus,
)

log = logging.getLogger(__name__)


class GiftCardError(Exception):
    pass


class InvalidCode(GiftCardError):
    pass


class CardNotActive(GiftCardError):
    pass


class InsufficientBalance(GiftCardError):
    pass


class AlreadyClaimed(GiftCardError):
    pass


# ─── Issue ─────────────────────────────────────────────────────────────────

def issue(amount, *, currency: str = 'AOA',
          purchased_by=None, expires_at: datetime | None = None,
          actor=None) -> tuple[GiftCard, str]:
    """Mint a new card. Returns (card, plaintext_code). The plaintext is
    shown ONCE and never recoverable — caller hands it to the buyer."""
    amount = Decimal(str(amount or 0))
    if amount <= 0:
        raise GiftCardError('amount must be positive')

    # Generate-and-store with collision retry. SHA-256 over a 12-char
    # alphabet-restricted code has ~60 bits of effective entropy — a
    # genuine collision is astronomically unlikely, but retry is cheap.
    for _attempt in range(5):
        plaintext = GiftCard.generate_code()
        h = GiftCard.hash_code(plaintext)
        prefix = plaintext.split('-', 1)[1][:4]  # first 4 chars after GIFT-
        with transaction.atomic():
            try:
                card = GiftCard.objects.create(
                    code_hash=h, code_prefix=prefix,
                    initial_value=amount, current_balance=amount,
                    currency=currency.upper(),
                    purchased_by=purchased_by if (purchased_by and getattr(purchased_by, 'is_authenticated', False)) else None,
                    expires_at=expires_at,
                )
                GiftCardTransaction.objects.create(
                    card=card, kind=GiftCardTransactionKind.ISSUE,
                    amount=amount, balance_after=amount,
                    actor=actor if (actor and getattr(actor, 'is_authenticated', False)) else None,
                    dedupe_key=f'issue:{card.pk}',  # one-issue-per-card
                )
                return card, plaintext
            except IntegrityError:
                # code_hash collision — astronomically rare, but retry.
                continue
    raise GiftCardError('failed to allocate unique gift card code')


# ─── Claim ─────────────────────────────────────────────────────────────────

def claim(plaintext_code: str, user) -> GiftCard:
    """Bind a card to a user. Anyone with the code can claim; once claimed,
    only that user can redeem."""
    if not (user and getattr(user, 'is_authenticated', False)):
        raise GiftCardError('user required')

    h = GiftCard.hash_code((plaintext_code or '').strip())
    with transaction.atomic():
        card = GiftCard.objects.select_for_update().filter(code_hash=h).first()
        if card is None:
            raise InvalidCode('unknown or invalid gift card code')
        if card.status != CardStatus.ACTIVE:
            raise CardNotActive(f'card is {card.status}')
        if card.expires_at and card.expires_at < timezone.now():
            raise CardNotActive('card has expired')
        if card.claimed_by_id is not None:
            if card.claimed_by_id != user.id:
                raise AlreadyClaimed('card already claimed by another user')
            # Idempotent: re-claiming by the same user is a no-op
            return card
        card.claimed_by = user
        card.claimed_at = timezone.now()
        card.save(update_fields=['claimed_by', 'claimed_at', 'updated_at'])
        GiftCardTransaction.objects.create(
            card=card, kind=GiftCardTransactionKind.CLAIM,
            amount=Decimal('0'), balance_after=card.current_balance,
            actor=user, dedupe_key=f'claim:{card.pk}',
            note=f'claimed by user {user.id}',
        )
    _publish('giftcard.claimed', card)
    return card


# ─── Redeem ────────────────────────────────────────────────────────────────

def redeem(card: GiftCard, amount, *, ref_type: str = '',
           ref_id: str = '', actor=None,
           note: str = '') -> GiftCardTransaction:
    """Debit ``amount`` from the card. Refuses on insufficient balance
    OR non-active status. Idempotent per (card, kind=redeem, ref)."""
    amount = Decimal(str(amount or 0))
    if amount <= 0:
        raise GiftCardError('amount must be positive')

    dedupe = (f'redeem:{ref_type}:{ref_id}'
              if ref_type and ref_id else None)

    with transaction.atomic():
        c = GiftCard.objects.select_for_update().get(pk=card.pk)

        # Idempotency pre-check — we hold the card row lock so a
        # concurrent retry can't slip past the SELECT. Catching
        # IntegrityError as a fallback would NOT work inside
        # transaction.atomic(): the failed INSERT marks the whole
        # transaction broken and subsequent queries fail.
        if dedupe:
            existing = GiftCardTransaction.objects.filter(
                card=c, dedupe_key=dedupe,
            ).first()
            if existing is not None:
                return existing

        if c.status != CardStatus.ACTIVE:
            raise CardNotActive(f'card is {c.status}')
        if c.expires_at and c.expires_at < timezone.now():
            raise CardNotActive('card has expired')
        if c.current_balance < amount:
            raise InsufficientBalance(
                f'insufficient balance: have {c.current_balance}, need {amount}'
            )
        new_balance = c.current_balance - amount
        tx = GiftCardTransaction.objects.create(
            card=c, kind=GiftCardTransactionKind.REDEEM,
            amount=-amount, balance_after=new_balance,
            ref_type=ref_type[:40], ref_id=str(ref_id)[:80],
            dedupe_key=dedupe, actor=actor, note=note[:200],
        )

        c.current_balance = new_balance
        if new_balance == 0:
            c.status = CardStatus.REDEEMED
        c.save(update_fields=['current_balance', 'status', 'updated_at'])

    _publish('giftcard.redeemed', c, extra={'amount': str(amount)})
    return tx


# ─── Refund ────────────────────────────────────────────────────────────────

def refund_redemption(card: GiftCard, amount, *,
                      original_ref_type: str, original_ref_id: str,
                      actor=None, note: str = '') -> GiftCardTransaction:
    """Credit ``amount`` back to the card. Used when an order paid with
    this card is refunded. Status flips back to ACTIVE if it was REDEEMED.

    Idempotent per (card, original ref) — repeated refunds for the same
    original redemption produce one row.
    """
    amount = Decimal(str(amount or 0))
    if amount <= 0:
        raise GiftCardError('amount must be positive')

    dedupe = f'refund:{original_ref_type}:{original_ref_id}'

    with transaction.atomic():
        c = GiftCard.objects.select_for_update().get(pk=card.pk)

        # Idempotency pre-check inside the locked block
        existing = GiftCardTransaction.objects.filter(
            card=c, dedupe_key=dedupe,
        ).first()
        if existing is not None:
            return existing

        if c.status == CardStatus.CANCELLED:
            raise CardNotActive('card was cancelled — refund must go elsewhere')
        new_balance = c.current_balance + amount
        applied_amount = amount
        # Cap at the initial value — over-refunding is a bug somewhere.
        if new_balance > c.initial_value:
            log.warning(
                'gift card refund exceeds initial: card=%s, refund=%s, '
                'current=%s, initial=%s — clamping',
                c.pk, amount, c.current_balance, c.initial_value,
            )
            new_balance = c.initial_value
            # Stored amount = ACTUAL credit applied. The note records the
            # requested amount for forensics. Without this fix, the ledger
            # sum diverges from current_balance — the very property gift
            # card audits depend on.
            applied_amount = new_balance - c.current_balance
        tx = GiftCardTransaction.objects.create(
            card=c, kind=GiftCardTransactionKind.REFUND,
            amount=applied_amount, balance_after=new_balance,
            ref_type=original_ref_type[:40], ref_id=str(original_ref_id)[:80],
            dedupe_key=dedupe, actor=actor,
            note=(f'requested {amount}, applied {applied_amount}: {note}'
                  if applied_amount != amount else note)[:200],
        )

        c.current_balance = new_balance
        # Re-activate a fully-redeemed card on refund
        if c.status == CardStatus.REDEEMED and new_balance > 0:
            c.status = CardStatus.ACTIVE
        c.save(update_fields=['current_balance', 'status', 'updated_at'])
    return tx


# ─── Admin adjustment ──────────────────────────────────────────────────────

def adjust(card: GiftCard, *, delta, note: str = '', actor) -> GiftCardTransaction:
    """Admin-only positive or negative adjustment. Bypasses dedupe so
    multiple adjustments stack. Always audited via the actor field."""
    delta = Decimal(str(delta or 0))
    if delta == 0:
        raise GiftCardError('delta must be non-zero')
    with transaction.atomic():
        c = GiftCard.objects.select_for_update().get(pk=card.pk)
        new_balance = c.current_balance + delta
        if new_balance < 0:
            raise InsufficientBalance(
                f'adjustment would go negative: {c.current_balance} + {delta}'
            )
        tx = GiftCardTransaction.objects.create(
            card=c, kind=GiftCardTransactionKind.ADJUST,
            amount=delta, balance_after=new_balance,
            actor=actor, note=note[:200],
            # dedupe_key=None bypasses uniqueness (admin may stack)
        )
        c.current_balance = new_balance
        if new_balance == 0 and c.status == CardStatus.ACTIVE:
            c.status = CardStatus.REDEEMED
        elif new_balance > 0 and c.status == CardStatus.REDEEMED:
            c.status = CardStatus.ACTIVE
        c.save(update_fields=['current_balance', 'status', 'updated_at'])
    return tx


# ─── Expiry ────────────────────────────────────────────────────────────────

def expire_overdue_cards(batch_size: int = 200) -> dict:
    """Walk ACTIVE cards past expires_at with positive balance; final
    EXPIRE transaction zeros them out and flips status to EXPIRED."""
    now = timezone.now()
    qs = (
        GiftCard.objects
        .filter(status=CardStatus.ACTIVE, expires_at__lt=now,
                current_balance__gt=0)
        .order_by('expires_at')[:batch_size]
    )
    expired_count = 0
    for c in qs:
        try:
            with transaction.atomic():
                c2 = GiftCard.objects.select_for_update().get(pk=c.pk)
                if c2.status != CardStatus.ACTIVE or c2.current_balance <= 0:
                    continue
                forfeited = c2.current_balance
                GiftCardTransaction.objects.create(
                    card=c2, kind=GiftCardTransactionKind.EXPIRE,
                    amount=-forfeited, balance_after=Decimal('0'),
                    note='expired — balance forfeited',
                    dedupe_key=f'expire:{c2.pk}',
                )
                c2.current_balance = Decimal('0')
                c2.status = CardStatus.EXPIRED
                c2.save(update_fields=['current_balance', 'status', 'updated_at'])
            expired_count += 1
        except Exception:
            log.exception('expire card %s failed', c.pk)
    return {'expired': expired_count}


# ─── Helpers ──────────────────────────────────────────────────────────────

def lookup(plaintext_code: str) -> GiftCard | None:
    """Constant-time lookup by plaintext code. Returns None if unknown."""
    h = GiftCard.hash_code((plaintext_code or '').strip())
    return GiftCard.objects.filter(code_hash=h).first()


def _publish(topic: str, card: GiftCard, extra: dict | None = None):
    try:
        from apps.outbox.service import publish
        payload = {
            'card_id': card.id, 'code_prefix': card.code_prefix,
            'currency': card.currency, 'balance': str(card.current_balance),
            'status': card.status,
            'claimed_by': card.claimed_by_id,
        }
        if extra:
            payload.update(extra)
        publish(topic=topic, payload=payload,
                dedupe_key=f'{topic}:{card.id}:{int(timezone.now().timestamp())}',
                ref_type='gift_card', ref_id=str(card.id))
    except Exception:
        log.debug('outbox publish failed: %s', topic, exc_info=True)
