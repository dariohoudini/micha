"""
Outbox handlers for the orders domain.

Auto-imported by apps.outbox.OutboxConfig.ready() at startup.
"""
import logging

from apps.outbox.handlers import handler

logger = logging.getLogger('outbox.handlers.orders')


@handler('order.protection_lapsed_pending')
def on_protection_lapsed_pending(payload):
    """Seller never confirmed within the deadline. Auto-cancel + refund buyer.

    Money path:
      • Payment may already have hit gateway (status=pending here means the
        buyer paid but the seller didn't confirm — money is in escrow).
      • Refund the buyer to their store credit. Cash refund to gateway is a
        separate operator decision.
    """
    from django.db import transaction
    from apps.orders.models import Order
    order_id = payload.get('order_id')
    if not order_id:
        return
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return
        if order.status != 'pending':
            return  # already moved on
        order.update_status(
            'cancelled',
            note='Auto-cancelled — seller did not confirm within 48h (Buyer Protection).'
        )
        order.protection_state = 'broken'
        order.save(update_fields=['protection_state'])
        # Refund to store credit
        try:
            from apps.ledger.service import record_refund_to_buyer
            from django.contrib.auth import get_user_model
            from django.db.models import F
            User = get_user_model()
            record_refund_to_buyer(
                order=order, amount=order.total,
                refund_id=f'protection-{order.id}',
                destination='store_credit',
            )
            User.objects.filter(pk=order.buyer_id).update(
                store_credit=F('store_credit') + order.total,
            )
        except Exception:
            logger.exception(f'Refund failed during protection lapse for {order_id}')
            raise  # let outbox retry


@handler('order.protection_lapsed_unshipped')
def on_protection_lapsed_unshipped(payload):
    """Seller confirmed but never shipped. Same outcome as unconfirmed."""
    from django.db import transaction
    from apps.orders.models import Order
    order_id = payload.get('order_id')
    if not order_id:
        return
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return
        if order.status not in ('confirmed', 'processing'):
            return
        order.update_status(
            'cancelled',
            note='Auto-cancelled — seller did not ship within 7 days (Buyer Protection).'
        )
        order.protection_state = 'broken'
        order.save(update_fields=['protection_state'])
        try:
            from apps.ledger.service import record_refund_to_buyer
            from django.contrib.auth import get_user_model
            from django.db.models import F
            User = get_user_model()
            record_refund_to_buyer(
                order=order, amount=order.total,
                refund_id=f'protection-{order.id}',
                destination='store_credit',
            )
            User.objects.filter(pk=order.buyer_id).update(
                store_credit=F('store_credit') + order.total,
            )
        except Exception:
            logger.exception(f'Refund failed during protection lapse for {order_id}')
            raise


@handler('order.protection_lapsed_in_transit')
def on_protection_lapsed_in_transit(payload):
    """Order shipped but not confirmed delivered after 30 days.

    Treat as delivered (start the post-delivery protection window). This is
    the AliExpress pattern — keeps the buyer protected while not blocking
    the seller's escrow indefinitely.
    """
    from django.db import transaction
    from apps.orders.models import Order
    order_id = payload.get('order_id')
    if not order_id:
        return
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return
        if order.status != 'shipped':
            return
        order.update_status(
            'delivered',
            note='Auto-marked delivered after 30 days in transit (Buyer Protection).'
        )


@handler('order.protection_completed')
def on_protection_completed(payload):
    """60-day post-delivery protection window passed. Move to completed."""
    from django.db import transaction
    from apps.orders.models import Order
    order_id = payload.get('order_id')
    if not order_id:
        return
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return
        if order.status != 'delivered':
            return
        order.protection_state = 'completed'
        order.protection_deadline_at = None
        order.save(update_fields=['protection_state', 'protection_deadline_at'])


@handler('order.delivery_confirmed')
def on_order_delivery_confirmed(payload):
    """Buyer (or auto-action) marked delivered — release escrow → seller wallet.

    Idempotent: release_order_escrow itself is keyed on
    Escrow(order_id, status='holding'), so re-running is a no-op once
    the escrow has been released.
    """
    order_id = payload.get('order_id')
    if not order_id:
        return
    from apps.orders.tasks import release_order_escrow
    try:
        release_order_escrow(order_id)
    except Exception:
        logger.exception(f'release_order_escrow failed for {order_id}')
        raise  # outbox retry


@handler('order.shipped')
def on_order_shipped(payload):
    """Send the buyer their shipping notification (push + in-app)."""
    order_id = payload.get('order_id')
    if not order_id:
        return
    from apps.orders.tasks import send_shipping_notification
    try:
        send_shipping_notification(order_id)
    except Exception:
        logger.exception(f'send_shipping_notification failed for {order_id}')
        raise


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
