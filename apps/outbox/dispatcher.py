"""
Outbox dispatcher.

Drains pending OutboxEvent rows in FIFO order, runs each handler, and
records success / retry / dead state.

Concurrency safety
------------------
Uses `select_for_update(skip_locked=True)` so multiple workers can run
this in parallel without picking the same row twice.

Retry policy
------------
Exponential backoff with cap. Attempt N → wait 2**N seconds (60, 120, ...).
Capped at 1 hour. After `max_attempts` failures the event moves to DEAD;
operator must inspect / requeue.
"""
import logging
import traceback
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from .models import OutboxEvent, EventStatus
from .handlers import get_handlers

logger = logging.getLogger('outbox')

BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600


def _next_retry_delay(attempts):
    secs = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempts))
    return timedelta(seconds=secs)


def dispatch_one(event):
    """Run handlers for a single event. Caller already holds the row lock."""
    import time as _time
    from apps.telemetry import metrics as _m

    handlers = get_handlers(event.topic)
    if not handlers:
        # No handler is *not* an error — silently mark dispatched. New topics
        # may exist before code is wired up.
        logger.debug(f'No handler for topic {event.topic!r}, marking dispatched')
        event.status = EventStatus.DISPATCHED
        event.dispatched_at = timezone.now()
        event.save(update_fields=['status', 'dispatched_at', 'updated_at'])
        try:
            _m.outbox_dispatched.labels(topic=event.topic).inc()
        except Exception:
            pass
        return True

    _start = _time.monotonic()
    try:
        for fn in handlers:
            fn(event.payload)
    except Exception as e:
        event.attempts += 1
        event.last_error = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'[:5000]
        if event.attempts >= event.max_attempts:
            event.status = EventStatus.DEAD

            # Severity escalation on DEAD transition.
            #
            # The original code logged ``logger.error`` for every DEAD
            # event regardless of topic. Two problems with that:
            #
            #  1. Money-correctness topics (refund.*, payout.*,
            #     dispute.*, payment.*) reaching DEAD = money at risk.
            #     ERROR severity gets lost in normal alert noise;
            #     these need CRITICAL.
            #
            #  2. The error message didn't include the redacted
            #     payload context, so an on-call engineer had to query
            #     the DB to know what the failed event was about.
            #
            # The escalation classifies topic by prefix:
            #   refund.* / payout.* / dispute.* / payment.* → CRITICAL
            #   everything else → ERROR (existing behaviour)
            #
            # Payload is logged through the PII redactor to avoid
            # spilling buyer email / phone in the alert.
            is_critical_topic = (event.topic or '').split('.', 1)[0] in (
                'refund', 'payout', 'dispute', 'payment',
            )

            try:
                from middleware.pii_redactor import redact_value
                payload_safe = redact_value(event.payload or {})
            except Exception:
                payload_safe = '<redaction unavailable>'

            log_level = logger.critical if is_critical_topic else logger.error
            log_level(
                'outbox.event_dead',
                extra={
                    'event_id': str(event.id),
                    'topic': event.topic,
                    'attempts': event.attempts,
                    'payload': payload_safe,
                    'last_error': (event.last_error or '')[:500],
                    'ref_type': event.ref_type,
                    'ref_id': event.ref_id,
                    'severity_class': 'critical' if is_critical_topic else 'error',
                },
            )

            # Per-topic DEAD counter — separate metric from generic
            # dispatch_failed so alerts can target "events went DEAD"
            # specifically (vs the high-rate "individual attempt
            # failed" counter).
            try:
                _m.outbox_event_dead.labels(topic=event.topic).inc()
            except Exception:
                pass
        else:
            event.status = EventStatus.RETRYING
            event.next_attempt_at = timezone.now() + _next_retry_delay(event.attempts)
            logger.warning(
                f'Outbox event {event.id} ({event.topic}) failed attempt {event.attempts}, '
                f'retry at {event.next_attempt_at.isoformat()}'
            )
        event.save(update_fields=[
            'status', 'attempts', 'last_error', 'next_attempt_at', 'updated_at'
        ])
        try:
            _m.outbox_dispatch_failed.labels(topic=event.topic).inc()
            _m.outbox_dispatch_latency.observe(_time.monotonic() - _start)
        except Exception:
            pass
        return False

    # Success
    event.status = EventStatus.DISPATCHED
    event.dispatched_at = timezone.now()
    event.attempts += 1
    event.last_error = ''
    event.save(update_fields=[
        'status', 'attempts', 'last_error', 'dispatched_at', 'updated_at'
    ])
    try:
        _m.outbox_dispatched.labels(topic=event.topic).inc()
        _m.outbox_dispatch_latency.observe(_time.monotonic() - _start)
    except Exception:
        pass
    return True


def drain(batch_size=50):
    """Drain up to `batch_size` ready events. Returns count actually processed.

    Each event is locked + run in its own transaction. Safe for SLOW
    handlers (network calls etc.) because no event holds another event's
    row lock during a multi-second handler call.

    For fast handlers, see drain_batch() — batches under one outer
    transaction with per-event savepoints, ~Nx commit-cost reduction.
    """
    processed = 0
    now = timezone.now()
    for _ in range(batch_size):
        with transaction.atomic():
            event = (
                OutboxEvent.objects
                .select_for_update(skip_locked=True)
                .filter(
                    status__in=(EventStatus.PENDING, EventStatus.RETRYING),
                    next_attempt_at__lte=now,
                )
                .order_by('next_attempt_at', 'id')
                .first()
            )
            if event is None:
                break
            dispatch_one(event)
            processed += 1
    return processed


def drain_batch(batch_size=50):
    """Batched dispatch under ONE outer transaction with per-event savepoints.

    Trade-offs vs ``drain()``:
      + Single outer commit at the end → N-way reduction in commit cost.
        Postgres commit is the dominant write-path expense; for fast
        in-process handlers (the common case), throughput jumps 5-10x.
      - All ``batch_size`` rows are locked for the duration of the batch.
        Don't use this if any handler does multi-second network I/O —
        use drain() instead. (Rule of thumb: per-event-handler latency
        ≪ DB round-trip → drain_batch; otherwise → drain.)
      = Per-event error isolation preserved via savepoints. A handler
        raising mid-batch rolls back only its own savepoint; the other
        events' state changes commit normally at outer-tx commit.

    Returns count actually processed.
    """
    now = timezone.now()
    with transaction.atomic():
        events = list(
            OutboxEvent.objects
            .select_for_update(skip_locked=True)
            .filter(
                status__in=(EventStatus.PENDING, EventStatus.RETRYING),
                next_attempt_at__lte=now,
            )
            .order_by('next_attempt_at', 'id')[:batch_size]
        )
        processed = 0
        for event in events:
            sid = transaction.savepoint()
            try:
                dispatch_one(event)
                transaction.savepoint_commit(sid)
                processed += 1
            except Exception:
                # dispatch_one already records failure state on the
                # event — but if even that write failed, roll back the
                # savepoint to keep the outer tx healthy.
                transaction.savepoint_rollback(sid)
                logger.exception('drain_batch: dispatch_one raised for event %s',
                                  getattr(event, 'id', '?'))
        return processed
