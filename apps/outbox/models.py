"""
Transactional Outbox.

Why this exists
---------------
Inside a request handler we frequently want to (a) commit DB changes AND
(b) trigger async work — sending emails, push notifications, webhooks,
analytics events, etc. If we call `task.delay()` mid-transaction:

  • If DB commits but the broker is unreachable → the user never gets the
    confirmation email; the order is "silent".
  • If DB rolls back but the task was queued just before → an email goes
    out for an order that doesn't exist.

The outbox pattern solves this by treating the *intent to publish* as a
DB row written in the same transaction as the business write. A separate
worker reads the outbox and dispatches at-least-once. Network failure no
longer causes silent drops.

Lifecycle
---------
   pending  ──dispatch──→  dispatched
       │
       └──failure──┐
                   ▼
                 retrying ──exhausted──→ dead

Idempotency
-----------
Each event has a deterministic `dedupe_key` per (topic, ref_type, ref_id) +
purpose. Re-publishing with the same key is a no-op.
"""
from django.db import models
from django.utils import timezone


class EventStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    DISPATCHED = 'dispatched', 'Dispatched'
    RETRYING = 'retrying', 'Retrying'
    DEAD = 'dead', 'Dead (max attempts reached)'


class OutboxEvent(models.Model):
    """One row per intent-to-publish. Polled by the dispatcher."""
    topic = models.CharField(max_length=80, db_index=True,
                             help_text='e.g. "order.placed", "payment.confirmed"')
    payload = models.JSONField(default=dict)

    # Idempotency / dedupe — unique allows safe re-publish of the same intent
    dedupe_key = models.CharField(max_length=200, unique=True, db_index=True)

    # Optional reference to the business object that triggered the event
    ref_type = models.CharField(max_length=40, blank=True, db_index=True)
    ref_id = models.CharField(max_length=80, blank=True, db_index=True)

    status = models.CharField(
        max_length=12, choices=EventStatus.choices,
        default=EventStatus.PENDING, db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=10)

    # Scheduling: ready when next_attempt_at <= now()
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_attempt_at', 'id']
        indexes = [
            # The hot read path: "pending events ready to dispatch"
            models.Index(
                fields=['status', 'next_attempt_at'],
                name='outbox_pending_due_idx',
            ),
        ]

    def __str__(self):
        return f'{self.topic} · {self.status} · {self.dedupe_key}'
