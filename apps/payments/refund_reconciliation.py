"""
apps/payments/refund_reconciliation.py
───────────────────────────────────────

Detects and repairs the "gateway refunded but local state didn't catch
up" gap left open by gateway-first refund ordering (commit 9aa8879).

The gap, restated
──────────────────
PaymentProcessor.refund() now calls the gateway FIRST and only then
opens the local atomic block (wallet debit + Payment.status flip +
state machine transition + PaymentEvent log). This is the right
ordering — a gateway failure no longer leaves the wallet down.

But there's a residual window: gateway call succeeds, then the local
atomic block fails (DB connection drop, deadlock victim retry
exhaustion, pod OOM-killed mid-transaction). The gateway has the
canonical refund; our local state still says CONFIRMED. The buyer
got their money but the support team can't see it.

The fix: a reconciliation worker that looks for this gap and repairs
it. The signal is structural — PaymentEvent is immutable (its model
.delete() raises) and gets the gateway_refund_id at the start of the
atomic block. If we have a PaymentEvent('refunded' | 'refund_replay')
with a real gateway_refund_id, then EITHER the local block
also completed (Payment.status=REFUNDED) OR it failed and we need to
finish the work.

Public API
──────────
  reconcile_refunds(limit=200, window_hours=72) -> dict
      Scan recent refund-shaped PaymentEvent rows. For each whose
      Payment.status is NOT REFUNDED, call PaymentProcessor.refund()
      again — its gateway_refund_id idempotency replays the original
      and lets the local atomic block run to completion. Returns
      summary {checked, repaired, already_consistent, skipped, errors}.

  reconcile_refund_for_payment(payment) -> str
      Single-payment repair entry — used by ops endpoints / alert
      runbooks. Returns 'repaired' | 'already_consistent' | 'no_event'.

Why this is safe to run on a schedule
──────────────────────────────────────
The repair path calls PaymentProcessor.refund() which:
  • is idempotent at the gateway via the deterministic key
    'refund_<payment.id>_<amount>' (returns existing refund_id)
  • is idempotent locally (returns True early if Payment.status is
    already REFUNDED — no double-debit)

So a worker that runs every 5 minutes and re-processes a row that
was reconciled 5 seconds ago by another path is harmless. The cost
is a gateway round-trip (replay) and a PaymentEvent('refund_replay')
audit row — cheap.

Why this matters
─────────────────
Without this worker, the gateway-first ordering is "safe on failure"
in only one direction: we don't lose money. But we DO lose data
consistency — the marketplace shows the order as confirmed while
the buyer's card already saw the credit. Support gets confused.
Buyer can ask for ANOTHER refund. Worse: the seller's wallet still
has the order amount, which they can withdraw before we notice.

This worker closes the loop.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone


log = logging.getLogger(__name__)


# Event types whose presence indicates the gateway has confirmed a refund.
_REFUND_EVENT_TYPES = ('refunded', 'refund_replay')


def reconcile_refund_for_payment(payment) -> str:
    """Repair a single payment whose state may be out of sync with the
    gateway. Returns:
      • 'repaired'             — gap detected, fix attempted
      • 'already_consistent'   — local state matches gateway
      • 'no_event'             — no refund event found; not refunded
      • 'error'                — repair attempt raised; caller sees logs
    """
    from apps.payments.models import PaymentEvent
    from apps.payments.gateway import PaymentProcessor, PaymentState, PaymentGatewayError

    ev = (
        PaymentEvent.objects
        .filter(payment=payment, event_type__in=_REFUND_EVENT_TYPES)
        .order_by('-created_at')
        .first()
    )
    if ev is None:
        return 'no_event'

    if payment.status == PaymentState.REFUNDED:
        return 'already_consistent'

    # Drift detected. Re-run PaymentProcessor.refund() — the gateway
    # idempotency key replays the original refund_id; locally it'll
    # see CONFIRMED and finish the atomic block this time.
    details = ev.details or {}
    amount = details.get('amount')
    reason = details.get('reason', 'reconciliation_repair')
    try:
        from decimal import Decimal
        amt = Decimal(amount) if amount is not None else payment.amount
    except Exception:
        amt = payment.amount

    try:
        processor = PaymentProcessor()
        processor.refund(payment.order, amount=amt, reason=reason)
        log.warning(
            'refund reconciliation: repaired drift',
            extra={
                'payment_id': str(payment.pk),
                'order_id': str(payment.order_id),
                'gateway_refund_id': details.get('gateway_refund_id', ''),
                'amount': str(amt),
                'event_at': ev.created_at.isoformat(),
            },
        )
        return 'repaired'
    except PaymentGatewayError as e:
        log.error(
            'refund reconciliation: repair raised',
            extra={
                'payment_id': str(payment.pk),
                'order_id': str(payment.order_id),
                'gateway_refund_id': details.get('gateway_refund_id', ''),
                'error': str(e)[:500],
            },
        )
        return 'error'


def reconcile_refunds(*, limit: int = 200, window_hours: int = 72) -> dict:
    """Sweep recent refund-shaped PaymentEvent rows for drift.

    Eligibility:
      PaymentEvent.event_type IN ('refunded', 'refund_replay')
      AND PaymentEvent.created_at >= now - window_hours
      AND Payment.status != REFUNDED

    Capped at ``limit`` per call. Returns a structured summary.
    """
    from apps.payments.models import PaymentEvent
    from apps.payments.gateway import PaymentState
    from apps.orders.models import Payment

    since = timezone.now() - timedelta(hours=window_hours)

    # Find payment IDs that have a recent refund event AND are NOT in
    # REFUNDED state. One query — bound the scan window so this stays
    # cheap as the audit log grows.
    candidate_payment_ids = list(
        PaymentEvent.objects
        .filter(
            event_type__in=_REFUND_EVENT_TYPES,
            created_at__gte=since,
        )
        .order_by('-created_at')
        .values_list('payment_id', flat=True)
        .distinct()[:limit * 5]  # over-fetch because we re-filter below
    )

    if not candidate_payment_ids:
        return {
            'checked': 0, 'repaired': 0, 'already_consistent': 0,
            'no_event': 0, 'skipped': 0, 'errors': 0,
        }

    drifted = list(
        Payment.objects
        .filter(pk__in=candidate_payment_ids)
        .exclude(status=PaymentState.REFUNDED)
        .select_related('order')[:limit]
    )

    summary = {
        'checked': len(candidate_payment_ids),
        'repaired': 0,
        'already_consistent': 0,
        'no_event': 0,
        'skipped': 0,
        'errors': 0,
    }

    # Map per-row outcomes to summary keys. 'error' is singular at the
    # per-row layer but plural in the summary (count of errors), so
    # translate. An unrecognised outcome is counted as 'skipped' rather
    # than silently dropped — the absence would mask a bug here.
    _OUTCOME_TO_SUMMARY_KEY = {
        'repaired': 'repaired',
        'already_consistent': 'already_consistent',
        'no_event': 'no_event',
        'error': 'errors',
    }

    for pay in drifted:
        try:
            result = reconcile_refund_for_payment(pay)
            summary_key = _OUTCOME_TO_SUMMARY_KEY.get(result, 'skipped')
            summary[summary_key] += 1
        except Exception:
            log.exception('reconcile_refunds: payment %s exploded', pay.pk)
            summary['errors'] += 1

    log.info('reconcile_refunds complete', extra=summary)
    return summary
