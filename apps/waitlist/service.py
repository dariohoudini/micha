"""
apps/waitlist/service.py

Public entrypoints:

  join(user, product, variant_combo=None) → WaitlistEntry
    Idempotent: re-joining (user, product) when an active entry exists
    returns the existing row. Assigns next position in FIFO order.
    Refused if product is currently IN-STOCK — the user should just
    add to cart, not waitlist.

  leave(user, product) → bool
    Cancels the user's active entry. No-op when no active entry.

  notify_on_restock(product, batch_size=100)
    Fires alerts to the FIFO front of the waitlist when product has
    positive stock. Batches the notification so a viral restock with
    50k waitlisters doesn't thundering-herd the notification system —
    only ``batch_size`` are notified per call. Subsequent calls (beat
    every minute) drain the next batch.

  mark_converted(user, product, order_id)
    Called from the checkout flow when a previously-waitlisted user
    completes purchase. Stamps the entry's status → CONVERTED and
    records the order id for analytics.

  cleanup_stale(days=90)
    Beat task. Purges entries older than N days for products that
    are archived or where status is terminal (notified-but-never-
    converted past TTL, cancelled, etc.).
"""
from __future__ import annotations
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Max, F
from django.utils import timezone

from .models import WaitlistEntry, WaitlistStatus

log = logging.getLogger(__name__)


class WaitlistError(Exception):
    pass


# Rate-limit: how many entries we notify per restock-check tick.
# At 1-minute beat cadence: 100/min → 6,000/hr. A 100k-waitlister
# restock drains in ~17 hours; the early FIFO joiners get told first.
DEFAULT_NOTIFY_BATCH = 100

# Stale-purge defaults
STALE_DAYS_FOR_NOTIFIED = 14   # notified but never bought — assume lost
STALE_DAYS_FOR_WAITING  = 180  # waited 6 months — product probably gone


# ─── Join / leave ──────────────────────────────────────────────────────────

def join(user, product, variant_combo=None) -> WaitlistEntry:
    """Subscribe user to back-in-stock notification for this product."""
    if not (user and getattr(user, 'is_authenticated', False)):
        raise WaitlistError('user required')

    # Refuse if currently in stock — buyer should just add to cart.
    in_stock = (
        variant_combo.quantity if variant_combo
        else getattr(product, 'quantity', 0)
    ) > 0
    if in_stock:
        raise WaitlistError('product is in stock — add to cart instead')

    with transaction.atomic():
        # Idempotency: existing active entry → return it
        existing = WaitlistEntry.objects.filter(
            user=user, product=product, variant_combo=variant_combo,
            status=WaitlistStatus.WAITING,
        ).first()
        if existing is not None:
            return existing

        # Next position = max + 1 in this product's waitlist.
        # SELECT MAX is fine; the unique-active constraint prevents
        # double-join races, so positions never collide.
        next_pos = (
            WaitlistEntry.objects
            .filter(product=product)
            .aggregate(m=Max('position'))['m']
        )
        next_pos = (next_pos or 0) + 1

        entry = WaitlistEntry.objects.create(
            user=user, product=product, variant_combo=variant_combo,
            position=next_pos, status=WaitlistStatus.WAITING,
        )

    _publish('waitlist.joined', entry)
    return entry


def leave(user, product, variant_combo=None) -> bool:
    """Cancel a user's active waitlist entry. Returns True if there was
    one to cancel, False if not."""
    n = WaitlistEntry.objects.filter(
        user=user, product=product, variant_combo=variant_combo,
        status=WaitlistStatus.WAITING,
    ).update(status=WaitlistStatus.CANCELLED)
    return bool(n)


# ─── Notify on restock ─────────────────────────────────────────────────────

def notify_on_restock(product, *, batch_size: int = DEFAULT_NOTIFY_BATCH) -> dict:
    """Fire alerts to the FIFO front of the waitlist when product is
    back in stock.

    Returns: {'notified': N, 'remaining_waiting': N, 'available': N}.

    Rate-limit baked in: at most ``batch_size`` alerts per call.
    The beat task fires this on a 1-minute cadence so a viral restock
    drains gradually rather than spiking the notification system.
    """
    available = int(getattr(product, 'quantity', 0) or 0)
    if available <= 0:
        return {'notified': 0, 'remaining_waiting': 0, 'available': 0}

    # Don't notify more than what's in stock — wastes alert budget
    # on people who'll just see "now out of stock" again seconds later.
    notify_count = min(batch_size, available)

    with transaction.atomic():
        # Pick the FIFO front. Lock the rows so two concurrent restock-
        # checks don't double-notify.
        head = list(
            WaitlistEntry.objects
            .select_for_update(skip_locked=True)
            .filter(product=product, status=WaitlistStatus.WAITING)
            .order_by('position')[:notify_count]
        )
        if not head:
            return {'notified': 0, 'remaining_waiting': 0, 'available': available}

        now = timezone.now()
        WaitlistEntry.objects.filter(
            pk__in=[e.pk for e in head]
        ).update(status=WaitlistStatus.NOTIFIED, notified_at=now)

    # Outbox publish + AlertDelivery audit — outside the locked block.
    for entry in head:
        _publish('waitlist.notified', entry)
        _record_alert_delivery(entry)

    remaining = WaitlistEntry.objects.filter(
        product=product, status=WaitlistStatus.WAITING,
    ).count()
    return {'notified': len(head), 'remaining_waiting': remaining,
            'available': available}


def _record_alert_delivery(entry: WaitlistEntry):
    """Write an audit row in apps.alerts.AlertDelivery so the buyer's
    notification timeline is unified across alert kinds."""
    try:
        from apps.alerts.models import AlertDelivery, AlertKind, DeliveryChannel
        AlertDelivery.objects.create(
            user=entry.user, kind=AlertKind.BACK_IN_STOCK,
            channel=DeliveryChannel.OUTBOX,
            ref_type='waitlist_entry', ref_id=str(entry.id),
            product_ids=[str(entry.product_id)],
            payload={'product_id': str(entry.product_id),
                     'position': entry.position},
        )
    except Exception:
        log.debug('AlertDelivery write failed', exc_info=True)


# ─── Conversion tracking ───────────────────────────────────────────────────

def mark_converted(user, product, order_id: str) -> bool:
    """Called from the checkout flow when a notified waitlister actually
    buys. Updates their entry → CONVERTED so we can measure waitlist
    effectiveness."""
    n = WaitlistEntry.objects.filter(
        user=user, product=product,
        status=WaitlistStatus.NOTIFIED,
    ).update(
        status=WaitlistStatus.CONVERTED,
        converted_at=timezone.now(),
        converted_order_id=str(order_id)[:80],
    )
    return bool(n)


# ─── Cleanup ───────────────────────────────────────────────────────────────

def cleanup_stale(*, notified_days: int = STALE_DAYS_FOR_NOTIFIED,
                  waiting_days: int = STALE_DAYS_FOR_WAITING) -> dict:
    """Mark long-stale entries as EXPIRED. Beat task.

      • Notified but never converted past notified_days (default 14) →
        assume the buyer moved on
      • Waiting past waiting_days (default 180) → product is probably
        discontinued; clean up
    """
    now = timezone.now()
    notified_cutoff = now - timedelta(days=notified_days)
    waiting_cutoff = now - timedelta(days=waiting_days)

    n1 = WaitlistEntry.objects.filter(
        status=WaitlistStatus.NOTIFIED,
        notified_at__lt=notified_cutoff,
    ).update(status=WaitlistStatus.EXPIRED)

    n2 = WaitlistEntry.objects.filter(
        status=WaitlistStatus.WAITING,
        joined_at__lt=waiting_cutoff,
    ).update(status=WaitlistStatus.EXPIRED)

    return {'notified_expired': n1, 'waiting_expired': n2}


# ─── Utils ─────────────────────────────────────────────────────────────────

def waitlist_size(product) -> int:
    """Count of active waiters — useful for forecasting / social proof."""
    return WaitlistEntry.objects.filter(
        product=product, status=WaitlistStatus.WAITING,
    ).count()


def _publish(topic: str, entry: WaitlistEntry):
    try:
        from apps.outbox.service import publish
        publish(
            topic=topic,
            payload={
                'entry_id': entry.id,
                'user_id': entry.user_id,
                'product_id': str(entry.product_id),
                'position': entry.position,
                'status': entry.status,
            },
            dedupe_key=f'{topic}:{entry.id}:{int(timezone.now().timestamp())}',
            ref_type='waitlist_entry', ref_id=str(entry.id),
        )
    except Exception:
        log.debug('outbox publish failed: %s', topic, exc_info=True)
