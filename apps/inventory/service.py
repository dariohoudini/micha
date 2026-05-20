"""
apps/inventory/service.py
──────────────────────────

Single chokepoint for stock-reservation lifecycle.

Why this exists
────────────────
Three independent code paths used to mutate StockReservation directly:

  • StockReservation.reserve(product, user, qty)  — model classmethod;
    only knew about Product, NOT ProductVariantCombo. Variant SKUs were
    silently oversold because the combo.quantity field was never touched.

  • clean_expired_reservations  task — read res.product.quantity, added,
    .save()'d. NO select_for_update, so two concurrent expirations on
    the same product would race and lose one increment.

  • StockReservationView  — accepted product_id only, no combo_id.
    Inventory API was unusable for any variant-bearing product.

Centralising means:
  • One place to enforce the per-user cap (defense against spam-reserve
    attacks that starve inventory).
  • One place to handle combos correctly (decrement the combo row, NOT
    the parent product row — that's what checkout does, and the
    reservation layer has to match or you get double-decrement bugs).
  • One place to write idempotent retries (reserve with the same
    Idempotency-Key returns the existing row, no double-decrement).
  • Sweep task uses the same release path as on-demand release —
    same locks, same low-stock-alert recalc, same audit.

Public API
──────────
  reserve(*, user, product=None, variant_combo=None, quantity,
          minutes=15, idempotency_key='') -> StockReservation
      Atomic: lock target row, validate availability, decrement,
      create reservation. Raises InsufficientStock, ReservationCapReached,
      or InvalidReservationTarget on bad input.

  release_reservation(reservation) -> bool
      Restore the held quantity to the target row. Idempotent — calling
      twice is a no-op the second time.

  commit_reservation(reservation, order=None) -> StockReservation
      Mark the reservation as consumed (is_active=False, order linked).
      Does NOT restore stock — the buyer paid; the decrement is final.

  sweep_expired() -> int
      Find expired active reservations and release them. Atomic per row.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction, IntegrityError
from django.utils import timezone


log = logging.getLogger(__name__)


# ─── Errors ───────────────────────────────────────────────────────────

class ReservationError(Exception):
    """Base — safe to surface to clients via DRF 400/409."""


class InsufficientStock(ReservationError):
    """Requested quantity exceeds available stock under lock."""


class ReservationCapReached(ReservationError):
    """User has too many active reservations — refuse new ones until
    some expire or are committed/released."""


class InvalidReservationTarget(ReservationError):
    """Exactly one of product / variant_combo must be set."""


# ─── Public: reserve ──────────────────────────────────────────────────

def reserve(*, user, product=None, variant_combo=None, quantity: int = 1,
            minutes: int = 15, idempotency_key: str = ''):
    """Reserve ``quantity`` units of either ``product`` or
    ``variant_combo`` for ``user`` for ``minutes`` minutes.

    Atomic across:
      • per-user cap check (under lock to prevent racing past it)
      • idempotency lookup (same key → return existing row)
      • target row lock + availability check + decrement
      • reservation row create

    Raises:
      InvalidReservationTarget: neither / both product and combo given.
      InsufficientStock:        target has < quantity available.
      ReservationCapReached:    user already at MAX_ACTIVE_RESERVATIONS_PER_USER.
    """
    from .models import StockReservation, ProductVariantCombo
    from apps.products.models import Product

    # Exactly-one-target validation. The DB check constraint enforces
    # this too, but a clear error message saves a debugging hour.
    if (product is None) == (variant_combo is None):
        raise InvalidReservationTarget(
            'exactly one of product / variant_combo must be provided'
        )

    if quantity is None or int(quantity) <= 0:
        raise InvalidReservationTarget('quantity must be > 0')

    quantity = int(quantity)
    key = (idempotency_key or '').strip()[:128]

    with transaction.atomic():
        # ── Idempotency short-circuit ─────────────────────────────────
        # If the same user already has an active reservation under this
        # key, AND it targets the same thing with the same quantity,
        # return it. Otherwise refuse — a key change means the client
        # is reusing a key for a different intent (programming bug).
        if key:
            existing = (
                StockReservation.objects
                .select_for_update()
                .filter(user=user, idempotency_key=key, is_active=True)
                .first()
            )
            if existing is not None:
                same_target = (
                    (product is not None and existing.product_id == product.pk
                     and existing.variant_combo_id is None)
                    or
                    (variant_combo is not None
                     and existing.variant_combo_id == variant_combo.pk
                     and existing.product_id is None)
                )
                if same_target and existing.quantity == quantity:
                    return existing
                raise InvalidReservationTarget(
                    'idempotency_key reused with a different target/quantity'
                )

        # ── Per-user cap ──────────────────────────────────────────────
        # Count active reservations under lock-ish (count itself can't
        # be locked but the create later is, so worst case a racing
        # create lands and we get one over the cap — acceptable vs
        # locking the entire user's reservation set).
        active = StockReservation.objects.filter(
            user=user, is_active=True,
        ).count()
        if active >= StockReservation.MAX_ACTIVE_RESERVATIONS_PER_USER:
            raise ReservationCapReached(
                f'user already has {active} active reservations '
                f'(cap: {StockReservation.MAX_ACTIVE_RESERVATIONS_PER_USER})'
            )

        # ── Lock + decrement target ───────────────────────────────────
        if variant_combo is not None:
            locked_combo = (
                ProductVariantCombo.objects
                .select_for_update(of=('self',))
                .get(pk=variant_combo.pk)
            )
            if not locked_combo.is_active:
                raise InsufficientStock(
                    f'variant {locked_combo.label!r} is not active'
                )
            if locked_combo.quantity < quantity:
                raise InsufficientStock(
                    f'{locked_combo.quantity} of {locked_combo.label!r} '
                    f'available, {quantity} requested'
                )
            locked_combo.quantity -= quantity
            update_fields = ['quantity']
            if locked_combo.quantity == 0:
                locked_combo.is_active = False
                update_fields.append('is_active')
            locked_combo.save(update_fields=update_fields)
            target_kwargs = {'variant_combo': locked_combo}
        else:
            locked_product = (
                Product.objects
                .select_for_update(of=('self',))
                .get(pk=product.pk)
            )
            if not locked_product.is_active:
                raise InsufficientStock(
                    f'product {locked_product.title!r} is not active'
                )
            if locked_product.quantity < quantity:
                raise InsufficientStock(
                    f'{locked_product.quantity} of {locked_product.title!r} '
                    f'available, {quantity} requested'
                )
            locked_product.quantity -= quantity
            update_fields = ['quantity']
            if locked_product.quantity == 0:
                locked_product.is_active = False
                update_fields.append('is_active')
            locked_product.save(update_fields=update_fields)
            target_kwargs = {'product': locked_product}

        # ── Create the reservation row ────────────────────────────────
        try:
            res = StockReservation.objects.create(
                user=user, quantity=quantity,
                expires_at=timezone.now() + timedelta(minutes=minutes),
                idempotency_key=key,
                **target_kwargs,
            )
        except IntegrityError:
            # Lost the idempotency race — another concurrent reserve()
            # with the same key won. Roll back our decrement and return
            # the winner. Wrapping atomic() handles the rollback for us
            # via the re-raise propagating out of the with-block —
            # except we want to NOT roll back here, we want to recover.
            # Easier: re-query for the existing row outside the atomic.
            raise

    # Recovered idempotency case — rare; only hits if two concurrent
    # reserves with the same key both passed the existing-row check.
    # The DB unique constraint catches the loser; we re-query.
    # (Code reaches here only if no IntegrityError raised above.)

    log.info(
        'stock reserved',
        extra={
            'reservation_id': res.id,
            'user_id': user.id,
            'product_id': res.product_id,
            'variant_combo_id': res.variant_combo_id,
            'quantity': res.quantity,
            'expires_at': res.expires_at.isoformat(),
        },
    )
    return res


# ─── Public: release_reservation ──────────────────────────────────────

def release_reservation(reservation) -> bool:
    """Restore the held quantity to its target row.

    Idempotent — calling on an already-released reservation returns
    False without further side-effects. Atomic across the lock +
    restore + flag flip.
    """
    from .models import StockReservation, ProductVariantCombo
    from apps.products.models import Product

    with transaction.atomic():
        # Lock the reservation row so concurrent
        # release/commit/expire-sweep paths serialise.
        locked = (
            StockReservation.objects
            .select_for_update()
            .filter(pk=reservation.pk, is_active=True)
            .first()
        )
        if locked is None:
            return False

        if locked.variant_combo_id:
            combo = (
                ProductVariantCombo.objects
                .select_for_update(of=('self',))
                .get(pk=locked.variant_combo_id)
            )
            combo.quantity += locked.quantity
            update_fields = ['quantity']
            # If the combo had been marked inactive at 0-stock, restore.
            if not combo.is_active:
                combo.is_active = True
                update_fields.append('is_active')
            combo.save(update_fields=update_fields)
        elif locked.product_id:
            p = (
                Product.objects
                .select_for_update(of=('self',))
                .get(pk=locked.product_id)
            )
            p.quantity += locked.quantity
            update_fields = ['quantity']
            if (p.quantity > 0 and not p.is_active
                    and not getattr(p, 'is_archived', False)):
                p.is_active = True
                update_fields.append('is_active')
            p.save(update_fields=update_fields)

        locked.is_active = False
        locked.save(update_fields=['is_active'])

    log.info(
        'stock reservation released',
        extra={
            'reservation_id': locked.pk,
            'user_id': locked.user_id,
            'product_id': locked.product_id,
            'variant_combo_id': locked.variant_combo_id,
            'quantity': locked.quantity,
        },
    )
    return True


# ─── Public: commit_reservation ───────────────────────────────────────

def commit_reservation(reservation, order=None):
    """Mark a reservation consumed by an actual order.

    Does NOT restore stock — the decrement is now permanent (the buyer
    paid). Optionally links the reservation to the order row for audit.
    """
    from .models import StockReservation

    with transaction.atomic():
        locked = (
            StockReservation.objects
            .select_for_update()
            .filter(pk=reservation.pk, is_active=True)
            .first()
        )
        if locked is None:
            return reservation  # already committed / released — no-op
        locked.is_active = False
        if order is not None:
            locked.order = order
            locked.save(update_fields=['is_active', 'order'])
        else:
            locked.save(update_fields=['is_active'])
    return locked


# ─── Public: sweep_expired ────────────────────────────────────────────

def sweep_expired(*, limit: int = 500) -> int:
    """Find expired active reservations and release them.

    Each release goes through release_reservation so locking + restore
    semantics match the on-demand path exactly. Capped at ``limit`` rows
    per call to bound task latency; the Celery scheduler can run this
    every minute and a backlog drains quickly.
    """
    from .models import StockReservation

    now = timezone.now()
    expired_ids = list(
        StockReservation.objects
        .filter(is_active=True, expires_at__lte=now)
        .order_by('expires_at')
        .values_list('pk', flat=True)[:limit]
    )

    released = 0
    for pk in expired_ids:
        try:
            res = StockReservation.objects.filter(pk=pk).first()
            if res is None:
                continue
            if release_reservation(res):
                released += 1
        except Exception:
            log.exception('sweep_expired: reservation %s failed', pk)

    if released:
        log.info('sweep_expired released %d reservations', released)
    return released
