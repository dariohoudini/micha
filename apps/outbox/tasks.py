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


def _dlq_thresholds() -> dict:
    """Severity-escalation thresholds for the periodic DLQ health
    check. Read from settings so ops can tune without a redeploy."""
    from django.conf import settings
    return {
        # Number of DEAD events at which the periodic check escalates
        # from WARNING (>0) to CRITICAL.
        'critical_dead_count': int(
            getattr(settings, 'OUTBOX_DLQ_CRITICAL_DEAD_COUNT', 10)
        ),
        # Number of DEAD events that have been DEAD for more than
        # OLDEST_AGE_CRITICAL_SECONDS — "we've left them rotting".
        'critical_oldest_age_seconds': int(
            getattr(settings, 'OUTBOX_DLQ_CRITICAL_OLDEST_AGE', 3600)  # 1h
        ),
        # Stuck-retrying (24h+ in RETRYING state) events — handler is
        # almost certainly broken; needs ops triage.
        'critical_stale_retrying_count': int(
            getattr(settings, 'OUTBOX_DLQ_CRITICAL_STALE_RETRYING', 5)
        ),
    }


@shared_task(name='outbox.refresh_dlq_metrics')
@singleton_task('beat:outbox.refresh_dlq_metrics')
def refresh_dlq_metrics():
    """Update Prometheus gauges for DLQ-health monitoring + escalate
    severity in the structured log when thresholds are breached.

    Counters track flow (events dispatched / failed). Gauges track
    state (events currently dead, oldest-dead age, stuck-retry count).
    Both are needed: counters can't answer "is the DLQ growing?"
    without rate calculation.

    Severity escalation (NEW)
    ──────────────────────────
    The prior implementation logged WARNING for any dead > 0. That
    flattened the alert channel — 1 dead event looked the same as
    1000. Now:

      • No issues                                          INFO (silent)
      • dead in (0, critical_dead_count)                   WARNING
      • dead >= critical_dead_count                        CRITICAL
      • OR oldest_dead_age > critical_oldest_age_seconds   CRITICAL
      • OR stale_retrying >= critical_stale_retrying       CRITICAL

    Thresholds are tunable via settings:
      OUTBOX_DLQ_CRITICAL_DEAD_COUNT       (default 10)
      OUTBOX_DLQ_CRITICAL_OLDEST_AGE       (default 3600s = 1h)
      OUTBOX_DLQ_CRITICAL_STALE_RETRYING   (default 5)

    The CRITICAL severity is what triggers PagerDuty / Slack alerts
    in production logging pipelines (Datadog rule: severity=CRITICAL
    + logger=outbox → page on-call).

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

        thresholds = _dlq_thresholds()
        # Classify severity. CRITICAL when any of the three conditions
        # trip; WARNING for less-severe non-empty DLQ; INFO when clean.
        is_critical = (
            dead >= thresholds['critical_dead_count']
            or oldest_age > thresholds['critical_oldest_age_seconds']
            or stale_24h >= thresholds['critical_stale_retrying_count']
        )

        log_payload = {
            'dead': dead,
            'pending': pending,
            'oldest_dead_age_seconds': oldest_age,
            'stale_retrying_count_24h': stale_24h,
            'thresholds': thresholds,
        }

        if is_critical:
            log.critical(
                'outbox.dlq_health.CRITICAL',
                extra=log_payload,
            )
        elif dead > 0 or stale_24h > 0:
            log.warning(
                'outbox.dlq_health.degraded',
                extra=log_payload,
            )
        # Silent on clean state — INFO would just fill logs.

        log_payload['severity'] = (
            'critical' if is_critical
            else ('warning' if (dead > 0 or stale_24h > 0) else 'ok')
        )
        return log_payload
    except Exception:
        log.exception('outbox.refresh_dlq_metrics failed')
        return {'error': True}
