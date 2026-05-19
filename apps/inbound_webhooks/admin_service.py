"""
apps/inbound_webhooks/admin_service.py
──────────────────────────────────────

Operational tools for inbound webhooks. The decorator owns reception
+ verification + audit; this module owns post-hoc inspection +
re-processing.

Three real-world ops scenarios this addresses:

  • "Did we get a payment.confirmed for reference X?"
      → list_events(provider=..., event_type=..., reference=...)

  • "Our handler had a bug from 14:00–15:00. We just deployed the fix.
     Replay the webhooks that hit during that window."
      → replay_event(event_id) per event, or scripted via list_events
        filter + loop.

  • "The signature_invalid rate just spiked 100x. What's happening?"
      → recent_failures(severity='SIGNATURE_INVALID')

Replay semantics:
  • A REPLAYED event re-runs the registered handler with the same
    parsed payload that the original verifier produced.
  • The audit row's cached response is overwritten with the replay's
    outcome. Future provider-side replays of the same body will then
    see the new response (idempotency invariant preserved).
  • Replay is admin-triggered only. Provider-side replays continue
    to hit the byte-identical replay short-circuit in the decorator.
"""
from __future__ import annotations

import logging
import json
import time as _time
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import InboundWebhookEvent, WebhookStatus
from .verifiers import get_verifier


log = logging.getLogger(__name__)


class WebhookAdminError(Exception):
    pass


# ─── Inspect ─────────────────────────────────────────────────────────────

def list_events(*, provider: Optional[str] = None,
                event_type: Optional[str] = None,
                status: Optional[str] = None,
                reference: Optional[str] = None,
                since=None, limit: int = 50) -> list[dict]:
    """Filter the audit table.

    ``reference`` does a substring search in the body_excerpt — useful
    for "find the webhook for order_id=abc-xyz" style queries.
    """
    qs = InboundWebhookEvent.objects.all()
    if provider:
        qs = qs.filter(provider=provider)
    if event_type:
        qs = qs.filter(event_type=event_type)
    if status:
        qs = qs.filter(status=status)
    if reference:
        qs = qs.filter(body_excerpt__icontains=str(reference)[:80])
    if since is not None:
        qs = qs.filter(received_at__gte=since)
    qs = qs.order_by('-received_at')[:max(1, min(limit, 500))]
    return [_serialize(e) for e in qs]


def recent_failures(*, hours: int = 1, limit: int = 100) -> dict:
    """Group recent failures by status for the ops dashboard.

    Quick signal during an incident: "is the spike a single class
    of failure (one provider down, one signing key rotated) or
    scattered (something systemic)?"
    """
    cutoff = timezone.now() - timedelta(hours=max(1, hours))
    failure_statuses = (
        WebhookStatus.SIGNATURE_INVALID,
        WebhookStatus.MISSING_SIGNATURE,
        WebhookStatus.STALE_TIMESTAMP,
        WebhookStatus.MALFORMED,
        WebhookStatus.HANDLER_FAILED,
    )
    qs = InboundWebhookEvent.objects.filter(
        status__in=failure_statuses, received_at__gte=cutoff,
    )

    # Aggregate counts per (provider, status)
    from django.db.models import Count
    grouped = list(
        qs.values('provider', 'status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    samples = list(qs.order_by('-received_at')[:max(1, min(limit, 200))])
    return {
        'window_hours': hours,
        'total_failures': qs.count(),
        'grouped': grouped,
        'sample': [_serialize(e) for e in samples],
    }


def get_event(event_id) -> dict:
    """Single-event detail. Returns the full record including the
    body_excerpt and response_body. For deep triage."""
    e = InboundWebhookEvent.objects.filter(pk=event_id).first()
    if e is None:
        raise WebhookAdminError(f'event {event_id} not found')
    return _serialize(e, include_full=True)


# ─── Replay ──────────────────────────────────────────────────────────────

def replay_event(event_id, *, actor=None) -> dict:
    """Re-run the registered handler for an event.

    Use when a handler bug shipped, was fixed, and the operator wants
    to retroactively process events that failed (HANDLER_FAILED) or
    even successfully-processed events that did the wrong thing.

    Process:
      1. Look up the audit row + the registered handler function
         (via the per-provider verifier's normal flow).
      2. Re-parse the body_excerpt as JSON to reconstruct the payload.
         (We don't store the parsed payload separately — the excerpt
         IS the JSON body. For payloads > MAX_BODY_EXCERPT this is a
         truncation issue and we refuse.)
      3. Build a minimal request-like context and call the handler
         directly. We do NOT re-run signature verification — by the
         time this is replayed, the operator has decided trust.
      4. Update the audit row with the new outcome.

    Returns the updated event record.

    Limitations:
      • The handler must be importable by name. We resolve it via
        the views that the decorator wraps — i.e. we re-call the
        decorator-wrapped view with a synthesised request. This is
        coupled to the existing decorator implementation, so changes
        to the decorator MUST keep this replay-path working.
      • For body_excerpt-truncated events, replay refuses (operator
        sees an error and decides next step).
    """
    e = InboundWebhookEvent.objects.filter(pk=event_id).first()
    if e is None:
        raise WebhookAdminError(f'event {event_id} not found')
    if not e.body_excerpt:
        raise WebhookAdminError(
            f'event {event_id} has no body_excerpt — cannot replay'
        )

    # Re-parse the payload.
    try:
        payload = json.loads(e.body_excerpt)
    except Exception as exc:
        raise WebhookAdminError(
            f'event {event_id} body is not valid JSON; cannot replay '
            f'(orig parsed at receipt; storage truncation may have '
            f'corrupted): {exc}'
        )

    # Resolve the handler — look up by (provider, event_type) via the
    # outbox/inbound handler registry. This intentionally re-uses the
    # SAME registry the decorator pulls from, so a fix to the handler
    # is automatically picked up here.
    from .replay_registry import get_replay_handler
    handler = get_replay_handler(e.provider, e.event_type)
    if handler is None:
        raise WebhookAdminError(
            f'no replay handler registered for '
            f'provider={e.provider} event_type={e.event_type}'
        )

    start = _time.monotonic()
    try:
        result = handler(payload)
    except Exception as exc:
        log.exception('webhook replay handler raised: %s', exc)
        with transaction.atomic():
            e.status = WebhookStatus.HANDLER_FAILED
            e.response_status = 500
            e.response_body = json.dumps({'error': 'replay_handler_failed'})
            e.error = f'replay error: {type(exc).__name__}: {exc}'[:1000]
            e.duration_ms = int((_time.monotonic() - start) * 1000)
            e.save(update_fields=[
                'status', 'response_status', 'response_body',
                'error', 'duration_ms',
            ])
        log.warning(
            'webhook replay FAILED: id=%s provider=%s event_type=%s actor=%s',
            event_id, e.provider, e.event_type, getattr(actor, 'id', None),
        )
        return _serialize(e, include_full=True)

    with transaction.atomic():
        e.status = WebhookStatus.PROCESSED
        e.response_status = 200
        e.response_body = json.dumps({'status': 'replayed', 'result': result},
                                     default=str)[:4000]
        e.error = ''
        e.duration_ms = int((_time.monotonic() - start) * 1000)
        e.save(update_fields=[
            'status', 'response_status', 'response_body',
            'error', 'duration_ms',
        ])
    log.info(
        'webhook replay OK: id=%s provider=%s event_type=%s actor=%s',
        event_id, e.provider, e.event_type, getattr(actor, 'id', None),
    )
    return _serialize(e, include_full=True)


# ─── Stats ──────────────────────────────────────────────────────────────

def stats() -> dict:
    """Snapshot for monitoring + ops dashboard. Cheap aggregations."""
    from django.db.models import Count
    cutoff_1h = timezone.now() - timedelta(hours=1)
    cutoff_24h = timezone.now() - timedelta(hours=24)

    by_status_1h = list(
        InboundWebhookEvent.objects
        .filter(received_at__gte=cutoff_1h)
        .values('status').annotate(count=Count('id'))
        .order_by('-count')
    )
    by_provider_24h = list(
        InboundWebhookEvent.objects
        .filter(received_at__gte=cutoff_24h)
        .values('provider').annotate(count=Count('id'))
        .order_by('-count')
    )

    failure_statuses = (
        WebhookStatus.SIGNATURE_INVALID,
        WebhookStatus.MISSING_SIGNATURE,
        WebhookStatus.STALE_TIMESTAMP,
        WebhookStatus.MALFORMED,
        WebhookStatus.HANDLER_FAILED,
    )
    failures_1h = InboundWebhookEvent.objects.filter(
        status__in=failure_statuses, received_at__gte=cutoff_1h,
    ).count()
    total_1h = InboundWebhookEvent.objects.filter(
        received_at__gte=cutoff_1h,
    ).count()
    failure_rate = (failures_1h / total_1h) if total_1h > 0 else 0

    return {
        'by_status_1h': by_status_1h,
        'by_provider_24h': by_provider_24h,
        'total_1h': total_1h,
        'failures_1h': failures_1h,
        'failure_rate_1h': round(failure_rate, 4),
    }


# ─── Serialization ──────────────────────────────────────────────────────

def _serialize(e: InboundWebhookEvent, *, include_full: bool = False) -> dict:
    out = {
        'id': e.id,
        'provider': e.provider,
        'event_type': e.event_type,
        'status': e.status,
        'response_status': e.response_status,
        'received_at': e.received_at.isoformat(),
        'duration_ms': e.duration_ms,
        'source_ip': e.source_ip,
        'body_sha256_prefix': (e.body_sha256 or '')[:12],
    }
    if include_full:
        out.update({
            'body_excerpt': e.body_excerpt or '',
            'response_body': e.response_body or '',
            'error': e.error or '',
            'signature_header': (e.signature_header or '')[:80],
            'timestamp_header': e.timestamp_header,
            'user_agent': e.user_agent,
            'body_sha256': e.body_sha256,
        })
    return out
