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
import logging
from celery import shared_task
from .dispatcher import drain
from apps.core.task_locks import singleton_task


log = logging.getLogger(__name__)


@shared_task(name='outbox.drain', ignore_result=True)
def drain_task(batch_size=100):
    return drain(batch_size=batch_size)


@shared_task(name='outbox.refresh_dlq_metrics')
@singleton_task('beat:outbox.refresh_dlq_metrics')
def refresh_dlq_metrics():
    """Update Prometheus gauges for DLQ-health monitoring.

    Counters track flow (events dispatched / failed). Gauges track
    state (events currently dead, oldest-dead age, stuck-retry count).
    Both are needed: counters can't answer "is the DLQ growing?"
    without rate calculation.

    Wire as a 5-minute beat task so alerts fire fast enough that
    ops can intervene during business hours.
    """
    from . import dlq
    try:
        from apps.telemetry.metrics import (
            outbox_dead, outbox_pending,
            outbox_oldest_dead_age_seconds, outbox_stale_retrying,
        )
        from .models import OutboxEvent, EventStatus

        dead = dlq.dead_count()
        pending = OutboxEvent.objects.filter(
            status__in=(EventStatus.PENDING, EventStatus.RETRYING),
        ).count()
        oldest_age = dlq.oldest_dead_age_seconds()
        stale_24h = dlq.stale_retrying_count()

        outbox_dead.set(dead)
        outbox_pending.set(pending)
        outbox_oldest_dead_age_seconds.set(oldest_age)
        outbox_stale_retrying.set(stale_24h)

        # Log a single structured record so the on-call has a fast
        # "what's the outbox doing right now?" reference in the logs
        # even if Prometheus is unavailable.
        if dead > 0 or stale_24h > 0:
            log.warning(
                'outbox.dlq_health: dead=%d pending=%d oldest_dead_age=%ds '
                'stale_retrying_24h=%d',
                dead, pending, oldest_age, stale_24h,
            )
        return {
            'dead': dead, 'pending': pending,
            'oldest_dead_age_seconds': oldest_age,
            'stale_retrying_count_24h': stale_24h,
        }
    except Exception:
        log.exception('outbox.refresh_dlq_metrics failed')
        return {'error': True}
