"""
Outbox handlers for the orders domain.

Auto-imported by apps.outbox.OutboxConfig.ready() at startup.
"""
import logging

from apps.outbox.handlers import handler

logger = logging.getLogger('outbox.handlers.orders')


@handler('order.payment_confirmed')
def on_order_payment_confirmed(payload):
    """Send the buyer their order confirmation.

    Replaces the old `send_order_confirmation.delay()` call. The outbox
    guarantees this runs at-least-once even if the celery broker was
    unreachable when the order committed.

    Handler must be idempotent: it may run more than once if the
    dispatcher crashes between executing this and marking the event
    DISPATCHED. We delegate to the existing send_order_confirmation
    task implementation, which is already safe to re-run.
    """
    order_id = payload.get('order_id')
    if not order_id:
        logger.warning('order.payment_confirmed event with no order_id, skipping')
        return
    from apps.orders.tasks import send_order_confirmation
    # Run inline rather than .delay() — we're already in an async worker.
    # Calling .delay() would kick to a *different* queue, undoing the durability.
    try:
        send_order_confirmation(order_id)
    except Exception:
        logger.exception(f'send_order_confirmation failed for {order_id}')
        raise  # propagate so the outbox marks it for retry
