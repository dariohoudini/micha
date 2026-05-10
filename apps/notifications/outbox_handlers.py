"""
Notifications-domain outbox handlers.

Auto-imported by apps.outbox.OutboxConfig.ready() at startup.
"""
import logging

from apps.outbox.handlers import handler

logger = logging.getLogger('outbox.handlers.notifications')


@handler('broadcast.queued')
def on_broadcast_queued(payload):
    """Run the broadcast send. Idempotent — send_broadcast_task itself
    checks the broadcast.status and short-circuits if already sent.
    """
    broadcast_id = payload.get('broadcast_id')
    if not broadcast_id:
        return
    from apps.notifications.broadcast_tasks import send_broadcast_task
    try:
        send_broadcast_task(broadcast_id)
    except Exception:
        logger.exception(f'send_broadcast_task failed for {broadcast_id}')
        raise
