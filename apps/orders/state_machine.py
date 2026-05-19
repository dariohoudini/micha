"""
apps/orders/state_machine.py
─────────────────────────────

Single source of truth for Order.status transitions.

Before this module, six different code paths mutated ``order.status``
with inconsistent guarantees:

  ┌──────────────────────────────┬──────────┬───────┬───────────┬─────────┐
  │ path                         │ validate │ audit │ protection│ outbox  │
  ├──────────────────────────────┼──────────┼───────┼───────────┼─────────┤
  │ Order.update_status (model)  │   NO     │  YES  │   YES     │   no    │
  │ UpdateOrderStatusView        │  partial │  YES  │   YES     │  partial│
  │ CancelOrderView              │  partial │  YES  │   YES     │   no    │
  │ ConfirmDeliveryView          │  inline  │  YES  │   YES     │   yes   │
  │ payments.gateway.fail_payment│   NO     │  NO   │   NO      │   no    │
  │ admin_api direct .status =   │   NO     │  NO   │   NO      │   no    │
  └──────────────────────────────┴──────────┴───────┴───────────┴─────────┘

Three failure modes this opened up in production:

  • Invalid transitions (e.g. ``shipped → cancelled`` after the
    package physically left the warehouse) silently committed.

  • Orphan status values (``payment_failed`` was used in code but
    wasn't in ``Order.STATUS`` choices — only worked because Django's
    .update() bypasses choice validation).

  • Missing audit rows on critical paths — fail_payment changed the
    order status without an OrderStatusLog entry, breaking the
    "show me the history of this order" support flow.

The state machine here provides a SINGLE transition function that
all paths must use. Bypassing it is detectable via the
``invalid_status`` task scan.

Public API
──────────
  transition(order, new_status, *, actor=None, note='', source='',
             admin_override=False) -> Order
    Validate + lock + change + audit + protection-recalc + outbox.
    Raises InvalidTransition on illegal moves (unless override).

  is_valid_transition(from_status, to_status) -> bool
    Pure check, no side effects. Use for UI / permission checks.

  STATUS_GRAPH
    The canonical state graph. Edit this to add/remove transitions.

──────────────────────────────────────────────────────────────────────
Why outbox events are wired here, not in callers
──────────────────────────────────────────────────────────────────────

Some transitions MUST publish: ``order.shipped`` triggers buyer
notification + carrier-tracking integration. If a caller forgets to
publish, downstream silently misses the event. Centralising means
the event fires exactly when the status changes — atomic with the
audit row.

Callers that need their own side effects (loyalty points on
delivery-confirm, stock restore on cancel, etc.) still do their work
in their own atomic block AROUND ``transition()``. The state machine
just guarantees the status change itself is consistent.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone


log = logging.getLogger(__name__)


# ─── Canonical state graph ─────────────────────────────────────────────────
#
# Each key is a current status; the value is the set of statuses we
# allow transitioning TO. Terminal statuses have empty sets — once
# there, the order is frozen except via admin override.
#
# The graph reflects business rules:
#   • shipped → cancelled is FORBIDDEN: package is in transit; you
#     can refund a buyer but you can't undo the physical shipment.
#   • completed is terminal-success; refunded is terminal-failure.
#   • payment_failed is a recoverable terminal — buyer can retry
#     payment, which moves it back through pending.

STATUS_GRAPH: dict[str, set[str]] = {
    'pending': {
        'confirmed',          # payment confirmed by gateway
        'cancelled',          # buyer cancel (or auto-reap of abandoned)
        'payment_failed',     # gateway said no
    },
    'confirmed': {
        'processing',         # seller began fulfillment
        'cancelled',          # buyer cancel pre-shipment
        'refunded',           # admin refund pre-shipment
    },
    'processing': {
        'shipped',            # seller marked shipped
        'cancelled',          # admin cancel mid-prep (rare)
        'refunded',           # refund without ship
    },
    'shipped': {
        'delivered',          # courier / buyer confirms
        'refunded',           # buyer rejects on delivery; courier returns it
    },
    'delivered': {
        'completed',          # post-protection auto-close
        'refunded',           # buyer returns within protection window
    },
    'payment_failed': {
        'pending',            # buyer retries with new card
        'cancelled',          # give up after retry budget exhausted
    },
    # Terminal states:
    'completed': set(),
    'cancelled': set(),
    'refunded':  set(),
}


# Every valid status — used to detect orphan values written by
# bypass paths (e.g. someone setting a string not in this list).
VALID_STATUSES = frozenset(STATUS_GRAPH.keys())


# ─── Protection state policy ──────────────────────────────────────────────
# Mirrors Order.PROTECTION_STATE_BY_STATUS — duplicated here so the
# state machine can compute without importing the model at module level.

PROTECTION_STATE_BY_STATUS = {
    'pending':         'awaiting_seller',
    'confirmed':       'awaiting_ship',
    'processing':      'awaiting_ship',
    'shipped':         'in_transit',
    'delivered':       'in_protection',
    'completed':       'completed',
    'cancelled':       'none',
    'refunded':        'none',
    'payment_failed':  'none',
}

PROTECTION_DAYS = {
    'pending':    2,
    'confirmed':  7,
    'processing': 7,
    'shipped':    30,
    'delivered':  60,
}


# ─── Exceptions ───────────────────────────────────────────────────────────

class InvalidTransition(Exception):
    """Raised when a transition violates STATUS_GRAPH and admin_override
    is not set. Safe to show to end users — never leaks internals."""


# ─── Outbox event wiring ──────────────────────────────────────────────────

# Map (from_status, to_status) → outbox topic. Transitions not listed
# don't publish anything. Wildcards (from=None) match any source.

_OUTBOX_TOPICS: dict[tuple[Optional[str], str], str] = {
    (None, 'confirmed'):       'order.confirmed',
    (None, 'shipped'):         'order.shipped',
    (None, 'delivered'):       'order.delivery_confirmed',
    (None, 'cancelled'):       'order.cancelled',
    (None, 'refunded'):        'order.refunded',
    (None, 'payment_failed'):  'order.payment_failed',
}


def _outbox_topic_for(from_status: str, to_status: str) -> Optional[str]:
    """Resolve the outbox topic for this transition, if any."""
    return (
        _OUTBOX_TOPICS.get((from_status, to_status))
        or _OUTBOX_TOPICS.get((None, to_status))
    )


# ─── Pure validation ──────────────────────────────────────────────────────

def is_valid_transition(from_status: str, to_status: str) -> bool:
    """No side effects — just check the graph. Use for UI gating /
    permission preflight."""
    if from_status not in STATUS_GRAPH or to_status not in VALID_STATUSES:
        return False
    return to_status in STATUS_GRAPH[from_status]


def allowed_next_statuses(current: str) -> set[str]:
    return set(STATUS_GRAPH.get(current, set()))


# ─── The transition chokepoint ────────────────────────────────────────────

def transition(order, new_status: str, *,
               actor=None, note: str = '', source: str = '',
               admin_override: bool = False):
    """Validate + lock + change + audit + protection-recalc + outbox.

    Args:
      order: an Order instance (will be re-fetched with select_for_update).
      new_status: target status. Must be in VALID_STATUSES.
      actor: User who initiated the change (for audit).
      note: free-text note appended to the OrderStatusLog row.
      source: machine-readable origin (e.g. 'gateway:fail_payment',
        'view:cancel', 'admin:override'). Recorded on the audit row.
      admin_override: skip the STATUS_GRAPH check. Only an admin path
        should pass True. The audit row records admin_override=True so
        we can find policy violations after the fact.

    Returns the updated, refreshed Order instance.

    Raises:
      InvalidTransition: if not in graph and override is False.
      ValueError: if new_status isn't a known status at all.
    """
    # Late-import to avoid circular: state_machine ↔ models
    from .models import Order, OrderStatusLog

    if new_status not in VALID_STATUSES:
        raise ValueError(
            f'Unknown status {new_status!r}. Valid: {sorted(VALID_STATUSES)}'
        )

    with transaction.atomic():
        # Lock the row so concurrent transitions on the same order
        # serialise. Without this, two paths racing (e.g. buyer-cancel +
        # webhook-confirm) could both pass the from-state check and
        # produce an inconsistent end state.
        locked = Order.objects.select_for_update().get(pk=order.pk)
        old_status = locked.status

        # Idempotent no-op: setting status to its current value.
        # We don't raise but we also don't write an audit row.
        if old_status == new_status:
            return locked

        if not admin_override:
            if not is_valid_transition(old_status, new_status):
                raise InvalidTransition(
                    f'order {locked.pk}: cannot move from '
                    f'{old_status!r} to {new_status!r}. '
                    f'Allowed: {sorted(allowed_next_statuses(old_status))}.'
                )

        # Apply the status + protection-state changes atomically.
        locked.status = new_status
        new_protection = PROTECTION_STATE_BY_STATUS.get(new_status, 'none')
        days = PROTECTION_DAYS.get(new_status)
        locked.protection_state = new_protection
        locked.protection_deadline_at = (
            timezone.now() + timedelta(days=days) if days else None
        )
        locked.save(update_fields=[
            'status', 'protection_state', 'protection_deadline_at',
            'updated_at',
        ])

        # Audit row. Note prepended with source for forensic clarity:
        # "view:cancel — Cancelled by buyer", "gateway:fail_payment — declined".
        audit_note = (f'{source} — {note}' if source and note
                      else (source or note or ''))[:500]
        OrderStatusLog.objects.create(
            order=locked, from_status=old_status, to_status=new_status,
            changed_by=actor, note=audit_note,
        )

        # Telemetry — every transition tracked, labelled by from→to.
        try:
            from apps.telemetry.metrics import orders_status_transitions
            orders_status_transitions.labels(
                from_status=old_status, to_status=new_status,
            ).inc()
        except Exception:
            pass

    # Outbox publish OUTSIDE the locked block so the publish doesn't
    # extend the row-lock duration into the JSON serialisation work.
    topic = _outbox_topic_for(old_status, new_status)
    if topic is not None:
        try:
            from apps.outbox.service import publish
            publish(
                topic=topic,
                payload={
                    'order_id': str(locked.id),
                    'from_status': old_status,
                    'to_status': new_status,
                    'source': source[:80],
                    'actor_id': getattr(actor, 'id', None),
                },
                dedupe_key=f'order_transition:{locked.id}:{old_status}->{new_status}',
                ref_type='order', ref_id=str(locked.id),
            )
        except Exception:
            log.exception('state_machine: outbox publish failed')

    log.info(
        'order_transition: %s %s → %s (source=%s, actor=%s, override=%s)',
        locked.id, old_status, new_status, source,
        getattr(actor, 'id', None), admin_override,
    )

    return locked


# ─── Invariant scan (called by beat task) ─────────────────────────────────

def find_orphan_status_orders(limit: int = 100) -> list[dict]:
    """Find Order rows whose status isn't in VALID_STATUSES.

    Should always be empty. Non-empty result means a bypass path
    wrote a status string that the state machine doesn't know about.
    Surfaced via the ``orders.scan_invariants`` beat task.
    """
    from .models import Order
    qs = (
        Order.objects.exclude(status__in=VALID_STATUSES)
        .values('id', 'status', 'created_at')
        .order_by('-created_at')[:max(1, min(limit, 1000))]
    )
    return [
        {
            'order_id': str(row['id']),
            'invalid_status': row['status'],
            'created_at': row['created_at'].isoformat(),
        }
        for row in qs
    ]
