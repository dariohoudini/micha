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
    handlers = get_handlers(event.topic)
    if not handlers:
        # No handler is *not* an error — silently mark dispatched. New topics
        # may exist before code is wired up.
        logger.debug(f'No handler for topic {event.topic!r}, marking dispatched')
        event.status = EventStatus.DISPATCHED
        event.dispatched_at = timezone.now()
        event.save(update_fields=['status', 'dispatched_at', 'updated_at'])
        return True

    try:
        for fn in handlers:
            fn(event.payload)
    except Exception as e:
        event.attempts += 1
        event.last_error = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'[:5000]
        if event.attempts >= event.max_attempts:
            event.status = EventStatus.DEAD
            logger.error(
                f'Outbox event {event.id} ({event.topic}) DEAD after {event.attempts} attempts'
            )
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
        return False

    # Success
    event.status = EventStatus.DISPATCHED
    event.dispatched_at = timezone.now()
    event.attempts += 1
    event.last_error = ''
    event.save(update_fields=[
        'status', 'attempts', 'last_error', 'dispatched_at', 'updated_at'
    ])
    return True


def drain(batch_size=50):
    """Drain up to `batch_size` ready events. Returns count actually processed.

    Each event is locked via SELECT FOR UPDATE SKIP LOCKED so multiple
    dispatcher instances cooperate without contending or double-running.
    """
    processed = 0
    now = timezone.now()
    # Loop: each iteration locks-and-runs ONE event in its own transaction
    # so a slow handler can't hold a long lock and so failures of one
    # don't roll back others.
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
