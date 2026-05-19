"""Beat tasks for inbound webhook hygiene + monitoring."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.task_locks import singleton_task


log = logging.getLogger(__name__)


@shared_task(name='inbound_webhooks.refresh_metrics')
@singleton_task('beat:inbound_webhooks.refresh_metrics')
def refresh_webhook_metrics():
    """Update Prometheus gauges for webhook health.

    Failure rate over the last hour is the primary signal during
    incidents: a spike usually means either an attacker is probing
    or a deployed config rotated a signing key without redeploying
    the provider's webhook config.
    """
    from . import admin_service
    try:
        from apps.telemetry.metrics import (
            inbound_webhook_failure_rate_1h,
            inbound_webhook_failures_1h,
            inbound_webhook_total_1h,
        )
        s = admin_service.stats()
        inbound_webhook_failure_rate_1h.set(s['failure_rate_1h'])
        inbound_webhook_failures_1h.set(s['failures_1h'])
        inbound_webhook_total_1h.set(s['total_1h'])

        # Log a warning if the rate looks elevated. 5% is a reasonable
        # alert threshold for a healthy provider; if it's higher, ops
        # should look.
        if s['failure_rate_1h'] > 0.05:
            log.error(
                'inbound_webhooks: failure rate elevated %.2f%% '
                '(%d failures / %d total in last hour)',
                s['failure_rate_1h'] * 100,
                s['failures_1h'], s['total_1h'],
            )
        return s
    except Exception:
        log.exception('refresh_webhook_metrics failed')
        return {'error': True}


@shared_task(name='inbound_webhooks.purge_old')
@singleton_task('beat:inbound_webhooks.purge_old')
def purge_old_webhook_events():
    """Delete InboundWebhookEvent rows older than the retention window.

    Privacy: under GDPR / Angola's Lei 22/11, retaining source_ip +
    user_agent past forensic usefulness needs a justification. After
    90 days the forensic value is near-zero; the privacy cost stays.

    Storage: provider webhook volume scales with order volume; over
    a year a busy marketplace can write tens of millions of rows.

    Chunked so a million-row table doesn't lock.
    """
    from .models import InboundWebhookEvent
    days = int(getattr(settings, 'INBOUND_WEBHOOK_RETENTION_DAYS', 90))
    cutoff = timezone.now() - timedelta(days=days)
    deleted_total = 0
    while True:
        ids = list(
            InboundWebhookEvent.objects.filter(received_at__lt=cutoff)
            .values_list('pk', flat=True)[:5000]
        )
        if not ids:
            break
        deleted, _ = InboundWebhookEvent.objects.filter(pk__in=ids).delete()
        deleted_total += deleted
        if len(ids) < 5000:
            break
    log.info(
        'inbound_webhooks.purge_old: deleted=%s cutoff=%s',
        deleted_total, cutoff.isoformat(),
    )
    return {'deleted': deleted_total, 'cutoff': cutoff.isoformat()}
