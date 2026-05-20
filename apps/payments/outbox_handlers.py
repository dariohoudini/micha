"""
Payments-domain outbox handlers.

Auto-imported by apps.outbox.OutboxConfig.ready() at startup.
"""
import logging

from apps.outbox.handlers import handler

logger = logging.getLogger('outbox.handlers.payments')


@handler('payment.retry_scheduled')
def on_payment_retry(payload):
    """Run a delayed payment retry.

    Replaces the previous `retry_failed_payment.apply_async(countdown=300)`.
    The outbox dispatcher only picks this up when next_attempt_at is reached
    (5 minutes from publish), so the delay is preserved without a Celery
    broker schedule.
    """
    payment_id = payload.get('payment_id')
    if not payment_id:
        return
    from apps.payments.tasks import retry_failed_payment
    try:
        retry_failed_payment(payment_id)
    except Exception:
        logger.exception(f'retry_failed_payment failed for {payment_id}')
        raise


@handler('dispute.resolved')
def on_dispute_resolved(payload):
    """Drive the buyer refund immediately when a dispute resolves.

    Without this, a refund_buyer / partial_refund resolution writes a
    Refund(status='pending') row and waits for the periodic sweep
    (every 2 minutes by default). For high-priority dispute outcomes
    we want sub-second turnaround on the gateway call so the buyer's
    refund-pending notification matches the actual gateway state.

    Idempotent: process_refund itself is a no-op on terminal states,
    so duplicate outbox deliveries are safe.
    """
    resolution = payload.get('resolution')
    if resolution not in ('refund_buyer', 'partial_refund'):
        return  # pay_seller / dismissed don't owe the buyer money

    order_id = payload.get('order_id')
    if not order_id:
        return

    from apps.orders.models import Refund
    refunds = Refund.objects.filter(
        order_id=order_id, status__in=('pending', 'approved'),
    )
    from apps.payments.refund_service import process_refund
    for r in refunds:
        try:
            process_refund(r)
        except Exception:
            logger.exception('on_dispute_resolved: refund %s failed', r.pk)
            # Don't raise — the periodic sweep will retry. The outbox
            # event itself should mark as delivered so we don't infinite-
            # loop on a poison refund row.
