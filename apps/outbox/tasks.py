"""
Celery beat: drain the outbox every few seconds.

Wire in your celery beat schedule (config/celery.py or settings):

    CELERY_BEAT_SCHEDULE = {
        ...
        'outbox-drain': {
            'task': 'outbox.drain',
            'schedule': 5.0,  # every 5 seconds
        },
    }

If celery beat is not running, the management command `dispatch_outbox`
provides a manual / cron-driven fallback.
"""
from celery import shared_task
from .dispatcher import drain


@shared_task(name='outbox.drain', ignore_result=True)
def drain_task(batch_size=100):
    return drain(batch_size=batch_size)
