"""
apps/webhooks/outbox_handlers.py

Glue between the outbox and our SellerWebhook fanout. For each broadcastable
topic we register a tiny handler that:

  1. Resolves the relevant seller from the event payload
     (today: lookup Order.seller_id by order_id).
  2. Finds all active SellerWebhook rows subscribed to this topic + seller.
  3. Creates one WebhookDelivery row per match (idempotent via dedupe_key).
  4. Enqueues the delivery task.

The fanout itself is cheap and runs inside the outbox handler. The actual HTTP
call is deferred to a Celery task so a slow seller can't stall the dispatcher.
"""
import logging

from apps.outbox.handlers import handler
from .models import SellerWebhook, WebhookDelivery, ALLOWED_TOPICS

log = logging.getLogger(__name__)


def _seller_id_for(topic: str, payload: dict):
    """Return the seller_id (UUID/int) responsible for routing this event,
    or None if we cannot determine it (in which case nothing fans out)."""
    # Most order-scoped topics carry order_id; resolve via the Order row.
    order_id = payload.get('order_id') if isinstance(payload, dict) else None
    if order_id and topic.startswith(('order.', 'return.')):
        try:
            from apps.orders.models import Order
            return Order.objects.values_list('seller_id', flat=True).filter(pk=order_id).first()
        except Exception:
            return None
    if topic == 'payout.completed':
        # payout events should carry seller_id directly
        return payload.get('seller_id') if isinstance(payload, dict) else None
    return None


def _fanout(topic: str, payload: dict):
    """The actual fanout — called by the per-topic handlers below."""
    seller_id = _seller_id_for(topic, payload)
    if not seller_id:
        return  # not routable; silently no-op (other handlers still run)

    hooks = list(
        SellerWebhook.objects
        .filter(seller_id=seller_id, is_active=True)
    )
    # Filter in Python because topics is a JSONField list — index-friendly
    # filtering would require Postgres jsonb operators not portable to sqlite.
    hooks = [h for h in hooks if topic in (h.topics or [])]
    if not hooks:
        return

    # Stable dedupe: a given (event signature, webhook) maps to one delivery.
    # The outbox dedupe_key may not be in payload; we synthesise one from the
    # topic + a payload-derived stable id.
    event_sig = payload.get('order_id') or payload.get('event_id') or payload.get('payment_id') or ''
    if not event_sig:
        # fallback — hash of the payload itself
        from .models import canonical_payload
        import hashlib
        event_sig = hashlib.sha256(canonical_payload(payload)).hexdigest()[:32]

    from .tasks import deliver_webhook
    for h in hooks:
        dedupe = f'{topic}:{event_sig}:{h.id}'[:200]
        delivery, created = WebhookDelivery.objects.get_or_create(
            dedupe_key=dedupe,
            defaults={
                'webhook': h, 'topic': topic, 'payload': payload,
            },
        )
        if created:
            # Defer the actual HTTP call.
            try:
                deliver_webhook.delay(delivery.id)
            except Exception:
                # Celery unavailable in tests / sync paths — that's fine, the
                # row is in 'pending' and a periodic sweeper will pick it up.
                log.debug('deliver_webhook.delay failed; will be swept later')


# Register one handler per allowed topic. We do NOT use a wildcard because the
# outbox handler registry is per-topic by design.
def _register():
    def make(topic):
        @handler(topic)
        def _h(payload, _topic=topic):
            try:
                _fanout(_topic, payload)
            except Exception:
                # NEVER raise from this handler — would mark the outbox event
                # as failed for everyone, including handlers that succeeded.
                log.exception('webhook fanout failed for %s', _topic)
        return _h
    for t in ALLOWED_TOPICS:
        make(t)


_register()
