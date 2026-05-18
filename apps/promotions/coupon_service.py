"""
apps/promotions/coupon_service.py

Service-layer chokepoint for coupon validate/redeem/release.

Public entrypoints:

  validate(code, user, subtotal) -> (Coupon, Decimal discount)
    Pure read — no mutation. Checks every rule (active, window, total cap,
    per-user cap, min order, expiry). Returns the coupon and the discount
    the buyer WOULD get if they checked out now.

  redeem(coupon, user, *, order_id, subtotal) -> CouponRedemption
    Atomic decrement of available usage + audit row.
    INSIDE transaction.atomic() + SELECT FOR UPDATE on the coupon row,
    so concurrent redeems of the last available slot can't both win.
    Idempotent per (coupon, order_id) — retried checkout returns the
    existing redemption (no IntegrityError-in-atomic poisoning).

  release(coupon, order_id, *, actor=None, reason='') -> CouponRedemption | None
    Reverse a prior redemption (order cancelled / refunded). Decrements
    Coupon.used_count back. Idempotent — re-calling on an already-released
    redemption is a no-op.

  cleanup_expired() -> {soft_deactivated: int}
    Beat task — flips is_active=False on coupons past valid_until for
    cleaner admin queries. Doesn't delete (history needed for audit).

Why a separate service instead of methods on Coupon.is_valid /
calculate_discount? Because the existing model methods don't enforce
per-user caps, can't take a SELECT FOR UPDATE, and don't write the
audit row. The model methods are kept for the (read-only) frontend
validate view; the service is the only path that mutates state.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    Coupon, CouponRedemption, CouponRedemptionStatus,
)

log = logging.getLogger(__name__)


class CouponError(Exception):
    """Generic coupon failure — kept as base so callers can catch broadly."""


class CouponInvalid(CouponError):
    pass


class CouponExpired(CouponError):
    pass


class CouponExhausted(CouponError):
    pass


class CouponPerUserLimitReached(CouponError):
    pass


class CouponMinOrderNotMet(CouponError):
    pass


# ─── Validate (read-only) ──────────────────────────────────────────────────

def validate(code: str, user, subtotal) -> tuple[Coupon, Decimal]:
    """Return (coupon, discount) or raise.

    Used by both the cart preview API and as the first half of redeem().
    Does NOT mutate state — safe to call repeatedly on every cart edit.

    Per-user cap counts APPLIED redemptions only — released ones don't
    consume the user's allowance. (Otherwise an order cancellation would
    permanently burn a user's coupon entitlement, which is hostile.)
    """
    subtotal = Decimal(str(subtotal or 0))
    code = (code or '').strip()
    if not code:
        raise CouponInvalid('empty code')

    coupon = Coupon.objects.filter(code__iexact=code).first()
    if coupon is None:
        raise CouponInvalid('unknown code')

    if not coupon.is_active:
        raise CouponInvalid('coupon is inactive')

    now = timezone.now()
    if coupon.valid_from and now < coupon.valid_from:
        raise CouponExpired('coupon not yet active')
    if coupon.valid_until and now > coupon.valid_until:
        raise CouponExpired('coupon has expired')

    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        raise CouponExhausted('coupon fully redeemed')

    if subtotal < coupon.min_order_amount:
        raise CouponMinOrderNotMet(
            f'minimum order {coupon.min_order_amount} not met'
        )

    if user and user.is_authenticated and coupon.usage_limit_per_user:
        user_used = CouponRedemption.objects.filter(
            coupon=coupon, user=user,
            status=CouponRedemptionStatus.APPLIED,
        ).count()
        if user_used >= coupon.usage_limit_per_user:
            raise CouponPerUserLimitReached(
                f'per-user limit ({coupon.usage_limit_per_user}) reached'
            )

    discount = Decimal(str(coupon.calculate_discount(subtotal) or 0))
    # Final clamp: discount can never exceed subtotal (free_shipping → 0
    # which is fine; fixed > subtotal → already clamped in the model).
    if discount > subtotal:
        discount = subtotal
    return coupon, discount


# ─── Redeem (atomic) ──────────────────────────────────────────────────────

def redeem(coupon: Coupon, user, *, order_id: str, subtotal,
           note: str = '') -> CouponRedemption:
    """Atomic ledger insert + used_count increment, idempotent per
    (coupon, order_id). Re-validates inside the lock — between cart
    apply and checkout commit, the coupon may have been deactivated or
    fully consumed by another order.
    """
    if not order_id:
        raise CouponError('order_id is required for redeem')
    subtotal = Decimal(str(subtotal or 0))

    with transaction.atomic():
        c = Coupon.objects.select_for_update().get(pk=coupon.pk)

        # Idempotency pre-check — INSIDE the lock, BEFORE the INSERT.
        # If we tried to rely on IntegrityError from the unique constraint,
        # the failed INSERT would mark the whole transaction broken and
        # all subsequent queries would fail with InFailedSqlTransaction.
        # (See gift_cards/service.py for the same pattern + writeup.)
        existing = CouponRedemption.objects.filter(
            coupon=c, order_id=order_id,
        ).first()
        if existing is not None:
            if existing.status == CouponRedemptionStatus.APPLIED:
                return existing
            # Released previously — refuse to re-apply on the same order.
            # The caller should mint a new order or apply to a different one.
            raise CouponError(
                f'redemption for order {order_id} was previously released'
            )

        # Re-validate state inside the lock.
        now = timezone.now()
        if not c.is_active:
            raise CouponInvalid('coupon is inactive')
        if c.valid_until and now > c.valid_until:
            raise CouponExpired('coupon has expired')
        if c.usage_limit and c.used_count >= c.usage_limit:
            raise CouponExhausted('coupon fully redeemed')
        if subtotal < c.min_order_amount:
            raise CouponMinOrderNotMet(
                f'minimum order {c.min_order_amount} not met'
            )
        if c.usage_limit_per_user:
            user_used = CouponRedemption.objects.filter(
                coupon=c, user=user,
                status=CouponRedemptionStatus.APPLIED,
            ).count()
            if user_used >= c.usage_limit_per_user:
                raise CouponPerUserLimitReached(
                    f'per-user limit ({c.usage_limit_per_user}) reached'
                )

        discount = Decimal(str(c.calculate_discount(subtotal) or 0))
        if discount > subtotal:
            discount = subtotal

        redemption = CouponRedemption.objects.create(
            coupon=c, user=user, order_id=str(order_id)[:80],
            applied_amount=discount,
            subtotal_at_apply=subtotal,
            status=CouponRedemptionStatus.APPLIED,
            note=note[:200],
        )

        c.used_count = (c.used_count or 0) + 1
        c.save(update_fields=['used_count'])

    _publish('coupon.redeemed', c, {
        'order_id': order_id, 'user_id': user.id if user else None,
        'amount': str(discount), 'subtotal': str(subtotal),
        'redemption_id': redemption.id,
    })
    return redemption


# ─── Release (cancel / refund) ────────────────────────────────────────────

def release(coupon: Coupon, order_id: str, *,
            reason: str = '') -> CouponRedemption | None:
    """Undo a prior redemption — order cancelled or fully refunded.

    Decrements used_count and flips the audit row to RELEASED. Idempotent:
    a no-op if the redemption is already released or never existed.

    Why bother decrementing used_count? Because the total-cap semantics
    have to match operator expectation: a 100-use coupon where 30 orders
    got cancelled should still allow 100 successful redemptions, not 70.
    """
    with transaction.atomic():
        c = Coupon.objects.select_for_update().get(pk=coupon.pk)
        r = CouponRedemption.objects.select_for_update().filter(
            coupon=c, order_id=str(order_id)[:80],
        ).first()
        if r is None:
            return None
        if r.status == CouponRedemptionStatus.RELEASED:
            return r

        r.status = CouponRedemptionStatus.RELEASED
        r.released_at = timezone.now()
        r.note = (r.note + f' | released: {reason}')[:200] if reason else r.note
        r.save(update_fields=['status', 'released_at', 'note'])

        if c.used_count and c.used_count > 0:
            c.used_count -= 1
            c.save(update_fields=['used_count'])

    _publish('coupon.released', c, {
        'order_id': order_id, 'redemption_id': r.id,
        'amount': str(r.applied_amount),
    })
    return r


# ─── Cleanup ──────────────────────────────────────────────────────────────

def cleanup_expired(batch_size: int = 500) -> dict:
    """Soft-deactivate coupons past valid_until. Keeps admin views clean
    (operators usually want is_active=True as the default filter)
    without losing history."""
    now = timezone.now()
    qs = Coupon.objects.filter(
        is_active=True, valid_until__isnull=False, valid_until__lt=now,
    ).order_by('valid_until')[:batch_size]
    n = 0
    for c in qs:
        c.is_active = False
        c.save(update_fields=['is_active'])
        n += 1
    return {'soft_deactivated': n}


# ─── Outbox publish helper ────────────────────────────────────────────────

def _publish(topic: str, coupon: Coupon, extra: dict) -> None:
    try:
        from apps.outbox.service import publish
        publish(
            topic=topic,
            payload={
                'coupon_id': coupon.id,
                'code': coupon.code,
                'discount_type': coupon.discount_type,
                **extra,
            },
            dedupe_key=f'{topic}:{coupon.id}:{extra.get("order_id", "")}',
            ref_type='coupon', ref_id=str(coupon.id),
        )
    except Exception:
        log.debug('outbox publish failed for %s', topic, exc_info=True)
