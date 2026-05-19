"""
apps/outbox/dlq.py — Dead-letter queue management for the outbox.

The outbox dispatcher moves events to ``DEAD`` after ``max_attempts``
consecutive handler failures. That's the durability floor — better
to stop trying than to retry-storm forever — but ops needs tools to
TRIAGE dead events:

  • inspect them (what failed? why? what payload?)
  • fix the underlying problem (handler bug, downstream outage)
  • requeue them so they actually dispatch
  • discard the ones that are no longer relevant

Before this module, dead-event triage required raw SQL access in
production. At 3am during an incident that's not acceptable.

──────────────────────────────────────────────────────────────────────
Operations
──────────────────────────────────────────────────────────────────────

  list_dead(limit, topic=None, since=None)
    Returns the N most-recent DEAD events. Filter by topic
    (e.g. "order.shipped") and/or since-timestamp for focused triage.

  requeue(event_id, *, reset_attempts=True, actor=None)
    Move a single event back to PENDING for immediate redispatch.
    By default resets the attempts counter to 0 — assumes the
    operator has fixed the underlying issue. Set reset_attempts=False
    to give the event ONE more try with its existing count.

  requeue_bulk(*, topic=None, since=None, limit=1000, actor=None)
    Bulk requeue. Use with care — if the handler is still broken
    you'll just re-dead them. Always inspect a sample first.

  discard(event_id, *, reason='', actor=None)
    Permanently remove a DEAD event from the table. For events whose
    business context no longer applies (e.g. order was manually
    refunded; outbox notification for it is moot).

  stale_retrying(older_than=24h)
    List events stuck in RETRYING longer than the threshold. Often
    indicates a handler that silently returns success but doesn't
    actually do its work, OR a downstream service that always fails
    fast (each retry hits the max-backoff cap and stays there).

  dead_count()
    Returns the current count of DEAD events. Fed into the
    outbox_dead_count gauge by the beat task.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import OutboxEvent, EventStatus


log = logging.getLogger(__name__)


# ── Read helpers ───────────────────────────────────────────────────────────

def list_dead(*, limit: int = 50, topic: Optional[str] = None,
              since=None) -> list[dict]:
    """List the most-recent DEAD events for triage.

    Returns dicts (not model instances) so the response is JSON-safe
    and callers don't need to import the model.
    """
    qs = OutboxEvent.objects.filter(status=EventStatus.DEAD)
    if topic:
        qs = qs.filter(topic=topic)
    if since is not None:
        qs = qs.filter(updated_at__gte=since)
    qs = qs.order_by('-updated_at')[:max(1, min(limit, 500))]
    return [_serialize(e) for e in qs]


def stale_retrying(*, older_than: timedelta = timedelta(hours=24),
                   limit: int = 100) -> list[dict]:
    """Events in RETRYING that haven't transitioned in ``older_than``.

    Catches the silent-handler-bug class: handler returns without
    raising but doesn't actually do its work, the event cycles forever
    between RETRYING and the next retry attempt. Or a downstream
    service is hard-failing every time — the dispatcher keeps
    capping the backoff and never progresses.
    """
    cutoff = timezone.now() - older_than
    qs = (
        OutboxEvent.objects
        .filter(status=EventStatus.RETRYING, updated_at__lt=cutoff)
        .order_by('updated_at')[:max(1, min(limit, 500))]
    )
    return [_serialize(e) for e in qs]


def dead_count() -> int:
    return OutboxEvent.objects.filter(status=EventStatus.DEAD).count()


def oldest_dead_age_seconds() -> int:
    """Returns 0 if no dead events; otherwise age of the oldest DEAD
    event in seconds. Used for alerting — a single old dead event
    sitting unrequeued is a sign someone isn't watching the queue."""
    oldest = (
        OutboxEvent.objects.filter(status=EventStatus.DEAD)
        .order_by('updated_at')
        .values_list('updated_at', flat=True)
        .first()
    )
    if oldest is None:
        return 0
    return int((timezone.now() - oldest).total_seconds())


def stale_retrying_count(older_than: timedelta = timedelta(hours=24)) -> int:
    cutoff = timezone.now() - older_than
    return OutboxEvent.objects.filter(
        status=EventStatus.RETRYING, updated_at__lt=cutoff,
    ).count()


# ── Write helpers ──────────────────────────────────────────────────────────

class DLQError(Exception):
    pass


def requeue(event_id, *, reset_attempts: bool = True,
            actor=None) -> dict:
    """Move a single event back to PENDING.

    By default resets the attempts counter — the assumption is that
    the operator triggered this AFTER fixing the underlying problem.
    If they want to give the event one more try WITHOUT resetting
    (e.g. to confirm the handler now works without burning a retry
    if it fails), set reset_attempts=False.
    """
    with transaction.atomic():
        try:
            event = (
                OutboxEvent.objects
                .select_for_update()
                .get(pk=event_id)
            )
        except OutboxEvent.DoesNotExist:
            raise DLQError(f'event {event_id} does not exist')
        if event.status == EventStatus.DISPATCHED:
            raise DLQError(
                f'event {event_id} is already DISPATCHED; nothing to requeue'
            )
        update_fields = ['status', 'next_attempt_at', 'last_error']
        event.status = EventStatus.PENDING
        event.next_attempt_at = timezone.now()
        event.last_error = ''
        if reset_attempts:
            event.attempts = 0
            update_fields.append('attempts')
        event.save(update_fields=update_fields + ['updated_at'])

    log.info(
        'outbox.dlq.requeue: event=%s topic=%s actor=%s reset=%s',
        event.id, event.topic, getattr(actor, 'id', None), reset_attempts,
    )
    return _serialize(event)


def requeue_bulk(*, topic: Optional[str] = None,
                 since=None, limit: int = 1000,
                 reset_attempts: bool = True,
                 actor=None) -> dict:
    """Bulk-requeue DEAD events matching the filter.

    Returns a count + list of requeued IDs. Capped at ``limit`` so
    a runaway requeue can't take out the dispatcher with a million
    fresh PENDING events.
    """
    qs = OutboxEvent.objects.filter(status=EventStatus.DEAD)
    if topic:
        qs = qs.filter(topic=topic)
    if since is not None:
        qs = qs.filter(updated_at__gte=since)
    ids = list(qs.order_by('-updated_at').values_list('id', flat=True)[:limit])
    if not ids:
        return {'requeued': 0, 'ids': []}

    now = timezone.now()
    update_kwargs = dict(
        status=EventStatus.PENDING,
        next_attempt_at=now,
        last_error='',
    )
    if reset_attempts:
        update_kwargs['attempts'] = 0
    with transaction.atomic():
        OutboxEvent.objects.filter(pk__in=ids).update(**update_kwargs)

    log.info(
        'outbox.dlq.requeue_bulk: count=%d topic=%s actor=%s reset=%s',
        len(ids), topic, getattr(actor, 'id', None), reset_attempts,
    )
    return {'requeued': len(ids), 'ids': [str(i) for i in ids]}


def discard(event_id, *, reason: str = '', actor=None) -> dict:
    """Permanently remove a DEAD event.

    For events whose business context no longer applies (e.g. an
    order-confirmation email for an order that was already manually
    refunded; the notification is moot).
    """
    with transaction.atomic():
        try:
            event = (
                OutboxEvent.objects
                .select_for_update()
                .get(pk=event_id)
            )
        except OutboxEvent.DoesNotExist:
            raise DLQError(f'event {event_id} does not exist')
        if event.status not in (EventStatus.DEAD, EventStatus.RETRYING):
            raise DLQError(
                f'event {event_id} is in status={event.status}; '
                f'discard only applies to DEAD / RETRYING events'
            )
        snapshot = _serialize(event)
        event.delete()
    log.info(
        'outbox.dlq.discard: id=%s topic=%s actor=%s reason=%s',
        snapshot['id'], snapshot['topic'],
        getattr(actor, 'id', None), reason[:200],
    )
    snapshot['discarded'] = True
    snapshot['reason'] = reason
    return snapshot


# ── Serialization ──────────────────────────────────────────────────────────

def _serialize(event: OutboxEvent) -> dict:
    return {
        'id': str(event.id),
        'topic': event.topic,
        'status': event.status,
        'attempts': event.attempts,
        'max_attempts': event.max_attempts,
        'dedupe_key': event.dedupe_key,
        'ref_type': event.ref_type,
        'ref_id': event.ref_id,
        'next_attempt_at': event.next_attempt_at.isoformat() if event.next_attempt_at else None,
        'dispatched_at': event.dispatched_at.isoformat() if event.dispatched_at else None,
        'created_at': event.created_at.isoformat(),
        'updated_at': event.updated_at.isoformat(),
        'last_error': (event.last_error or '')[:2000],
        'payload': event.payload,
    }
