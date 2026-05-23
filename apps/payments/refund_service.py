"""
apps/payments/refund_service.py
────────────────────────────────

Drains Refund(status='pending') rows by routing each through
PaymentProcessor.refund() — the gateway path that actually credits
the buyer's card / Multicaixa Express wallet.

Why this exists
────────────────
Three code paths write Refund(status='pending'):

  • apps/orders/views.py  — buyer-initiated refund request
  • apps/disputes/service.py — dispute resolved to refund_buyer
  • apps/orders/saga_defs.py — return-flow refund issuance

Before this module, NOTHING drained those rows. They sat at 'pending'
until an ops engineer manually flipped them to 'processed' — which
mark the DB but never called the PSP, so the buyer's card was never
credited. The dispute commit (3812522) called this out as deferred;
this commit lands it.

Public API
──────────
  process_refund(refund) -> Refund
      Atomic single-refund processor. Locks the row, calls
      PaymentProcessor.refund(), updates status + retry metadata.
      Idempotent: a refund already in a terminal state is a no-op.

  process_pending_refunds(limit=200) -> dict
      Sweep entry point. Selects pending refunds eligible for
      processing (next_attempt_at <= now OR NULL), processes each.
      Returns a {processed, failed, deferred, skipped} summary.

Retry policy
─────────────
Exponential backoff with cap:
  attempt 1: process immediately
  attempt N (N>1): wait 60 * 2^(N-1) seconds, capped at 1 hour
  After max_attempts (default 8): mark 'failed', emit alert.

Time windows: 60s, 2m, 4m, 8m, 16m, 32m, 60m (capped) — total ~2h.

Error taxonomy
───────────────
Errors fall into two buckets that the worker treats differently:

  Permanent  → mark 'rejected' immediately, do NOT retry.
               Examples: "No confirmed payment found" — the order
               wasn't successfully paid in the first place. Retrying
               can't fix it.

  Transient  → schedule next_attempt_at + bump attempts. After
               max_attempts hit 'failed' (ops triage).
               Examples: gateway timeout, 5xx, network reset.

The discrimination is structural — we inspect the PaymentGatewayError
message. Add new permanent-error patterns to ``_PERMANENT_REASONS``
when the gateway introduces new error codes.

What this does NOT do
──────────────────────
Does not call the gateway directly — that's PaymentProcessor.refund()'s
job. This module is the orchestration / persistence layer.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone


log = logging.getLogger(__name__)


# ─── Retry policy ─────────────────────────────────────────────────────

BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 3600


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 60s, 2m, 4m, 8m, 16m, 32m, 60m+."""
    if attempts <= 1:
        return BACKOFF_BASE_SECONDS
    delay = BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
    return min(delay, BACKOFF_CAP_SECONDS)


# Permanent-error patterns: gateway responses that won't change on retry.
# Match against the lowercased error string. Conservative on purpose —
# better to retry a few times against a transient than to give up on a
# real outage.
_PERMANENT_REASONS = (
    'no confirmed payment',
    'payment not found',
    'order not refundable',
    'already refunded',
)


def _is_permanent_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(p in msg for p in _PERMANENT_REASONS)


# ─── Public: process_refund ───────────────────────────────────────────

def process_refund(refund) -> 'Refund':  # noqa: F821 — forward-reference string
    """Process a single Refund row through the gateway.

    Atomic across the lock + status update + audit. The gateway call
    itself is NOT in the atomic block — gateway latency would hold a
    DB row lock for tens of seconds, and a network-level retry would
    deadlock the worker pool.

    Idempotency
    ───────────
    Calls into PaymentProcessor.refund() which has its own 60s cache
    lock per payment + a check that payment.status == CONFIRMED. After
    the first successful refund, payment.status flips to REFUNDED and
    the second call raises "No confirmed payment found" — which we
    map to permanent (this row is done from the gateway's perspective).

    Returns the updated Refund row.
    """
    from apps.orders.models import Refund
    from apps.payments.gateway import PaymentProcessor, PaymentGatewayError

    now = timezone.now()

    with transaction.atomic():
        locked = Refund.objects.select_for_update().get(pk=refund.pk)
        if locked.status not in ('pending', 'approved'):
            # Terminal already — no-op.
            return locked
        locked.attempts = (locked.attempts or 0) + 1
        locked.last_attempt_at = now
        locked.save(update_fields=['attempts', 'last_attempt_at'])

    # Gateway call OUTSIDE the atomic block — see docstring.
    processor = PaymentProcessor()
    refund_failed = False
    err_repr = ''
    permanent = False
    try:
        ok = processor.refund(
            locked.order,
            amount=locked.amount,
            reason=(locked.reason or 'refund')[:200],
        )
        if not ok:
            refund_failed = True
            err_repr = 'PaymentProcessor.refund returned False'
    except PaymentGatewayError as e:
        refund_failed = True
        err_repr = f'PaymentGatewayError: {e}'
        permanent = _is_permanent_error(e)
    except Exception as e:
        refund_failed = True
        err_repr = f'{type(e).__name__}: {e}'
        log.exception('process_refund: unexpected exception for refund %s',
                      locked.pk)

    # Post-call status update — atomic again for the lock guarantee.
    with transaction.atomic():
        locked = Refund.objects.select_for_update().get(pk=locked.pk)

        if not refund_failed:
            locked.status = 'processed'
            locked.processed_at = timezone.now()
            locked.last_error = ''
            locked.next_attempt_at = None
            # Backfill gateway_refund_id from the PaymentEvent audit log
            # so reconciliation can join Refund rows to gateway records.
            # PaymentProcessor.refund logs the gateway_refund_id into
            # the 'refunded' (or 'refund_replay') event's details.
            try:
                from apps.payments.models import PaymentEvent
                from apps.orders.models import Payment
                pay = Payment.objects.filter(
                    order_id=locked.order_id,
                ).order_by('-created_at').first()
                if pay is not None:
                    ev = (
                        PaymentEvent.objects
                        .filter(
                            payment=pay,
                            event_type__in=('refunded', 'refund_replay'),
                        )
                        .order_by('-created_at')
                        .first()
                    )
                    if ev is not None:
                        gw_id = (ev.details or {}).get('gateway_refund_id', '')
                        if gw_id:
                            locked.gateway_refund_id = str(gw_id)[:128]
            except Exception:
                # Backfill is observability-only — never block the
                # success path on it.
                log.warning('refund: gateway_refund_id backfill failed',
                            exc_info=True)
            locked.save(update_fields=[
                'status', 'processed_at', 'last_error', 'next_attempt_at',
                'gateway_refund_id',
            ])
            log.info(
                'refund processed',
                extra={
                    'refund_id': locked.pk,
                    'order_id': str(locked.order_id),
                    'amount': str(locked.amount),
                    'attempts': locked.attempts,
                },
            )
            _publish('refund.processed', locked)
            return locked

        # Failed path.
        locked.last_error = err_repr[:2000]

        if permanent:
            locked.status = 'rejected'
            locked.next_attempt_at = None
            locked.save(update_fields=[
                'status', 'last_error', 'next_attempt_at',
            ])
            log.warning(
                'refund rejected (permanent)',
                extra={
                    'refund_id': locked.pk,
                    'order_id': str(locked.order_id),
                    'error': err_repr[:200],
                },
            )
            _publish('refund.rejected', locked, error=err_repr[:500])
            return locked

        # Transient — retry if under max_attempts, else hard-fail.
        if locked.attempts >= (locked.max_attempts or 0):
            locked.status = 'failed'
            locked.next_attempt_at = None
            locked.save(update_fields=[
                'status', 'last_error', 'next_attempt_at',
            ])
            log.error(
                'refund FAILED (max_attempts exhausted)',
                extra={
                    'refund_id': locked.pk,
                    'order_id': str(locked.order_id),
                    'attempts': locked.attempts,
                    'error': err_repr[:200],
                },
            )
            _publish('refund.failed', locked, error=err_repr[:500])
            return locked

        # Schedule retry.
        delay = _backoff_seconds(locked.attempts)
        locked.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        locked.save(update_fields=[
            'last_error', 'next_attempt_at',
        ])
        log.info(
            'refund deferred (transient)',
            extra={
                'refund_id': locked.pk,
                'attempts': locked.attempts,
                'next_attempt_in_seconds': delay,
                'error': err_repr[:200],
            },
        )
        return locked


# ─── Public: process_pending_refunds ──────────────────────────────────

def process_pending_refunds(*, limit: int = 200) -> dict:
    """Drain pending refunds eligible for processing.

    Eligibility:
      status IN ('pending', 'approved')
      AND (next_attempt_at IS NULL OR next_attempt_at <= now)
    Ordered by created_at — FIFO. Capped at ``limit`` per call.
    """
    from apps.orders.models import Refund

    now = timezone.now()
    eligible = (
        Refund.objects
        .filter(status__in=('pending', 'approved'))
        .filter(
            models_q_eligible(now)
        )
        .order_by('created_at')
        .values_list('pk', flat=True)[:limit]
    )

    summary = {'processed': 0, 'rejected': 0, 'failed': 0, 'deferred': 0, 'skipped': 0}
    for pk in list(eligible):
        try:
            row = Refund.objects.filter(pk=pk).first()
            if row is None:
                summary['skipped'] += 1
                continue
            updated = process_refund(row)
            if updated.status == 'processed':
                summary['processed'] += 1
            elif updated.status == 'rejected':
                summary['rejected'] += 1
            elif updated.status == 'failed':
                summary['failed'] += 1
            else:
                # Still pending — backoff scheduled.
                summary['deferred'] += 1
        except Exception:
            log.exception('process_pending_refunds: refund %s exploded', pk)
            summary['skipped'] += 1

    log.info('process_pending_refunds complete', extra=summary)
    return summary


# Helper to express eligibility as a single Q — pulled out because
# the worker query and ad-hoc queries (admin dashboards) need the
# same predicate.
def models_q_eligible(now):
    from django.db.models import Q
    return Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)


# ─── Outbox helper ────────────────────────────────────────────────────

def _publish(topic: str, refund, **extra):
    try:
        from apps.outbox.service import publish
        payload = {
            'refund_id': refund.pk,
            'order_id': str(refund.order_id),
            'amount': str(refund.amount),
            'attempts': refund.attempts,
            'status': refund.status,
        }
        payload.update(extra)
        publish(
            topic=topic,
            payload=payload,
            dedupe_key=f'{topic}:{refund.pk}:{refund.status}',
            ref_type='refund',
            ref_id=str(refund.pk),
        )
    except Exception:
        log.warning('refund: outbox publish %s failed', topic, exc_info=True)
