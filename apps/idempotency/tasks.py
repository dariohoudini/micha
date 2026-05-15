"""
apps/idempotency/tasks.py

Celery periodic task to delete expired idempotency keys. Keeps the table from
growing without bound — keys past their TTL are no longer eligible for replay
and just consume storage.
"""
import logging
from celery import shared_task
from django.utils import timezone

log = logging.getLogger(__name__)


@shared_task(name='idempotency.sweep_expired')
def sweep_expired():
    """Delete idempotency rows whose TTL has elapsed."""
    from .models import IdempotencyKey
    now = timezone.now()
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lt=now).delete()
    if deleted:
        log.info('idempotency.sweep_expired: deleted=%d', deleted)
    return deleted
