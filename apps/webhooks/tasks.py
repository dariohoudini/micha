"""
apps/webhooks/tasks.py

Celery task that POSTs a single WebhookDelivery to the seller's URL, with
HMAC signing, timeout, retry/backoff, auto-disable on persistent failure.
"""
import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import (
    WebhookDelivery, DeliveryStatus,
    sign_payload, canonical_payload,
    SIGNATURE_HEADER,
)

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 8
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600


def _next_retry_delay(attempts: int) -> timedelta:
    secs = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempts))
    return timedelta(seconds=secs)


def _post(url: str, body: bytes, signature: str, request_id: str):
    """Isolated HTTP call so tests can monkeypatch it cleanly."""
    import requests
    return requests.post(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            SIGNATURE_HEADER: signature,
            'X-Micha-Delivery': request_id,
            'User-Agent': 'MICHA-Webhooks/1.0',
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )


@shared_task(name='webhooks.deliver', bind=True, max_retries=0)
def deliver_webhook(self, delivery_id: int):
    """Attempt to deliver one WebhookDelivery. Idempotent — safe to call
    multiple times for the same id."""
    with transaction.atomic():
        d = (
            WebhookDelivery.objects
            .select_for_update(skip_locked=True)
            .select_related('webhook')
            .filter(pk=delivery_id)
            .first()
        )
        if not d:
            return  # locked by another worker, or row gone
        if d.status == DeliveryStatus.DELIVERED:
            return  # already done

        hook = d.webhook
        if not hook.is_active:
            # Webhook was disabled (e.g. by auto-disable). Mark dead so it
            # doesn't sit pending forever; admin can re-enable + requeue.
            d.status = DeliveryStatus.DEAD
            d.last_error = 'webhook_inactive'
            d.save(update_fields=['status', 'last_error', 'updated_at'])
            return

        body = canonical_payload(d.payload)
        ts = int(time.time())
        sig = sign_payload(hook.secret, ts, body)
        d.attempts += 1

        try:
            resp = _post(hook.url, body, sig, str(d.id))
            d.response_status = resp.status_code
            d.response_body = (resp.text or '')[:500]
        except Exception as e:
            d.response_status = None
            d.response_body = ''
            d.last_error = f'{type(e).__name__}: {e}'[:500]
            success = False
        else:
            # Anything 2xx counts as a successful delivery.
            success = 200 <= (d.response_status or 0) < 300
            if success:
                d.last_error = ''
            else:
                # Non-2xx — leave response_body for forensics, but also set
                # last_error so the ops queue can show *why* it failed at a
                # glance without parsing HTML/JSON response bodies.
                d.last_error = f'HTTP {d.response_status}'

        if success:
            d.status = DeliveryStatus.DELIVERED
            d.delivered_at = timezone.now()
            d.save(update_fields=[
                'status', 'attempts', 'response_status', 'response_body',
                'last_error', 'delivered_at', 'updated_at',
            ])
            try:
                hook.record_success()
            except Exception:
                pass
            return

        # Failure path — retry or dead-letter.
        if d.attempts >= d.max_attempts:
            d.status = DeliveryStatus.DEAD
            d.next_attempt_at = None
        else:
            d.status = DeliveryStatus.RETRYING
            d.next_attempt_at = timezone.now() + _next_retry_delay(d.attempts)
        d.save(update_fields=[
            'status', 'attempts', 'response_status', 'response_body',
            'last_error', 'next_attempt_at', 'updated_at',
        ])
        try:
            hook.record_failure()
        except Exception:
            pass


@shared_task(name='webhooks.sweep_retries')
def sweep_retries():
    """Pick up retrying / pending deliveries whose backoff has elapsed and
    re-queue them. Belt-and-braces complement to the per-task .delay()."""
    now = timezone.now()
    qs = (
        WebhookDelivery.objects
        .filter(status__in=(DeliveryStatus.PENDING, DeliveryStatus.RETRYING))
        .filter(
            # next_attempt_at IS NULL  OR  next_attempt_at <= now
            # We can't OR easily in a single queryset filter so do two passes.
        )
    )
    due_pending = qs.filter(status=DeliveryStatus.PENDING)
    due_retrying = qs.filter(status=DeliveryStatus.RETRYING, next_attempt_at__lte=now)
    ids = list(due_pending.values_list('id', flat=True)[:200]) + \
          list(due_retrying.values_list('id', flat=True)[:200])
    for did in ids:
        try:
            deliver_webhook.delay(did)
        except Exception:
            log.exception('failed to enqueue delivery %s', did)
    return len(ids)
