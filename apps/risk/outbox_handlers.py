"""
Risk-domain outbox handlers.

`fraud.flagged` events are emitted from CheckoutView whenever an
assessment lands above the FLAG threshold. Each handler is idempotent.
"""
import logging

from apps.outbox.handlers import handler

logger = logging.getLogger('outbox.handlers.risk')


@handler('fraud.flagged')
def on_fraud_flagged(payload):
    """Surface flagged orders to ops.

    For now: just log structured. Wiring to PagerDuty / Slack is a config
    change; the durable event is already in the outbox with retry.
    """
    logger.warning('fraud.flagged', extra={
        'order_ids': payload.get('order_ids'),
        'user_id': payload.get('user_id'),
        'score': payload.get('score'),
        'action': payload.get('action'),
        'reasons': payload.get('reasons'),
    })
