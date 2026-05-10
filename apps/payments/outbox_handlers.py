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
