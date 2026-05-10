"""
Outbox publishing API.

Usage from inside a transaction:

    from apps.outbox.service import publish

    with transaction.atomic():
        order = Order.objects.create(...)
        publish(
            topic='order.placed',
            payload={'order_id': str(order.id)},
            dedupe_key=f'order.placed:{order.id}',
            ref_type='order', ref_id=str(order.id),
        )

Idempotency: re-calling with the same `dedupe_key` is a no-op (returns the
existing event). Use a deterministic key per (topic, business_object,
purpose), e.g. `order.placed:<order_id>` or `cashback:<order_id>:awarded`.
"""
from .models import OutboxEvent


def publish(*, topic, payload=None, dedupe_key, ref_type='', ref_id='',
            max_attempts=10):
    """Insert an outbox row in the current transaction. Returns (event, created)."""
    if not topic:
        raise ValueError('topic is required')
    if not dedupe_key:
        raise ValueError('dedupe_key is required for idempotency')

    event, created = OutboxEvent.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            'topic': topic,
            'payload': payload or {},
            'ref_type': ref_type,
            'ref_id': str(ref_id)[:80] if ref_id else '',
            'max_attempts': max_attempts,
        },
    )
    if created:
        try:
            from apps.telemetry.metrics import outbox_published
            outbox_published.labels(topic=topic).inc()
        except Exception:
            pass
    return event, created
