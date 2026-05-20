"""
apps/inbound_webhooks/decorators.py

@verified_webhook(provider='appypay') — drop on any APIView.post that
receives a provider callback. Does the full defense-in-depth dance:

  1. Hash the body, look up by (provider, body_sha256) — if we've seen this
     exact body before, return the cached response (replay-safe). Critical:
     this short-circuits BEFORE running the handler again.

  2. Create an InboundWebhookEvent row in RECEIVED state with the raw
     signature header, source IP, user-agent. If the rest fails, this row
     is the forensic record.

  3. Run the provider's verifier (signature + timestamp window). On fail,
     stamp the row with the fail status and return 400 with a safe error
     (no info leak about *why* it failed beyond "bad signature").

  4. Run the wrapped handler with the parsed payload. Cache the response
     status + body into the row for future replays.

  5. Stamp duration, log security event on rejection. NEVER raises — a
     bug in the audit table writer must not break webhook reception.

This decorator is the only legitimate way to mount a provider webhook
endpoint. The pre-existing AppyPayWebhookView (with its own inline
verification) gets migrated to use this.
"""
from __future__ import annotations
import functools
import json
import logging
import time as _time

from django.http import HttpResponse
from django.db import IntegrityError, transaction
from rest_framework.response import Response

from .models import InboundWebhookEvent, WebhookStatus
from .verifiers import get_verifier

log = logging.getLogger(__name__)

# Cap body excerpt size — raw payloads from providers are typically small but
# we don't want to bloat the audit table if someone sends us 10MB of garbage.
MAX_BODY_EXCERPT = 4000


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()[:45]
    return (request.META.get('REMOTE_ADDR') or '')[:45]


def _safe_log_security(event_name, request, severity, details):
    try:
        from middleware.security import log_security_event
        log_security_event(event_name, request=request, severity=severity, details=details)
    except Exception:
        pass


def _response_for(status: int, body):
    """Return an HttpResponse — used for both fresh and replayed responses.
    Always emits JSON so providers get a consistent content-type."""
    if isinstance(body, (dict, list)):
        body_json = json.dumps(body, default=str)
    elif body is None:
        body_json = '{}'
    else:
        body_json = str(body)
    return HttpResponse(body_json, status=status, content_type='application/json')


def _max_body_bytes() -> int:
    """Per-webhook body size cap. Defaults to 64 KB — providers ship
    small JSON payloads; anything larger is almost certainly garbage
    or an attack. Override via settings.WEBHOOK_MAX_BODY_BYTES."""
    try:
        from django.conf import settings
        return int(getattr(settings, 'WEBHOOK_MAX_BODY_BYTES', 64 * 1024))
    except Exception:
        return 64 * 1024


def _allowed_ips_for(provider: str) -> set:
    """Source-IP allowlist for the given provider. Defence-in-depth:
    even if the signing secret leaks, an attacker who can't appear from
    the gateway's known egress IPs can't deliver forged webhooks.

    Configured via settings.WEBHOOK_ALLOWED_IPS — a dict mapping
    provider key to a list of IP strings:

        WEBHOOK_ALLOWED_IPS = {
            'appypay': ['41.x.y.z', '102.a.b.c'],
            'stripe':  ['54.187.174.169', ...],
        }

    Empty / missing entry = no IP enforcement for that provider
    (fail-open is acceptable because signature verification is the
    primary defence; this is the optional second layer).
    """
    try:
        from django.conf import settings
        mapping = getattr(settings, 'WEBHOOK_ALLOWED_IPS', {}) or {}
        return set(mapping.get(provider, []) or [])
    except Exception:
        return set()


def verified_webhook(provider: str):
    """Decorator factory. ``provider`` must match a verifier in the registry."""
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            start = _time.monotonic()

            # ── 0a. Body size cap ─────────────────────────────────────────
            # Read body length WITHOUT materialising the full payload first.
            # Django has already loaded request.body by this point (it's a
            # property that streams + caches), so we check the cached value's
            # size. The DATA_UPLOAD_MAX_MEMORY_SIZE Django setting is the
            # absolute outer bound; this cap is webhook-specific.
            body = request.body or b''
            if len(body) > _max_body_bytes():
                _safe_log_security(
                    'webhook_body_too_large', request, 'WARNING',
                    {'provider': provider, 'bytes': len(body),
                     'cap': _max_body_bytes()},
                )
                return _response_for(413, {'error': 'body_too_large'})

            # ── 0b. Source IP allowlist (defence-in-depth) ────────────────
            # When configured, ONLY accept webhooks from the known gateway
            # egress IPs. Empty list = no enforcement (signature verification
            # alone). When the secret leaks, this is the second wall.
            allowed = _allowed_ips_for(provider)
            if allowed:
                src_ip = _client_ip(request)
                if src_ip not in allowed:
                    _safe_log_security(
                        'webhook_ip_not_allowed', request, 'CRITICAL',
                        {'provider': provider, 'src_ip': src_ip,
                         'allowed_count': len(allowed)},
                    )
                    return _response_for(403, {'error': 'forbidden'})

            body_hash = InboundWebhookEvent.hash_body(body)
            signature_header = (
                request.META.get('HTTP_X_APPYPAY_SIGNATURE', '')
                or request.META.get('HTTP_STRIPE_SIGNATURE', '')
                or request.META.get('HTTP_VERIF_HASH', '')
            )[:500]
            timestamp_header = (
                request.META.get('HTTP_X_APPYPAY_TIMESTAMP', '')
                or ''
            )[:64]

            # ── 1. Replay short-circuit ──────────────────────────────────
            # If this exact (provider, body) was already received, return the
            # cached response. This is the storage-level guarantee that even
            # a perfectly-signed replay attack can't cause double execution.
            existing = (
                InboundWebhookEvent.objects
                .filter(provider=provider, body_sha256=body_hash)
                .only('id', 'response_status', 'response_body', 'status')
                .first()
            )
            if existing:
                # If the original was a hard fail (signature invalid, etc.) we
                # still want a fresh fail response — but we don't run the
                # handler. Replay the original outcome verbatim.
                _safe_log_security(
                    'webhook_replay_detected', request, 'INFO',
                    {'provider': provider, 'orig_status': existing.status,
                     'orig_id': existing.id},
                )
                return _response_for(
                    existing.response_status,
                    existing.response_body or {'status': 'replayed'},
                )

            # ── 2. Create the audit row ──────────────────────────────────
            ip = _client_ip(request)
            ua = (request.META.get('HTTP_USER_AGENT') or '')[:200]
            try:
                event = InboundWebhookEvent.objects.create(
                    provider=provider, body_sha256=body_hash,
                    body_excerpt=(body[:MAX_BODY_EXCERPT].decode('utf-8', errors='replace')),
                    signature_header=signature_header,
                    timestamp_header=timestamp_header,
                    source_ip=ip or None, user_agent=ua,
                    status=WebhookStatus.RECEIVED,
                )
            except IntegrityError:
                # A concurrent webhook hit us with the same body in the
                # tiny window between our SELECT and INSERT. Re-fetch and
                # serve as a replay.
                event = (
                    InboundWebhookEvent.objects
                    .filter(provider=provider, body_sha256=body_hash)
                    .first()
                )
                if event:
                    return _response_for(
                        event.response_status,
                        event.response_body or {'status': 'replayed'},
                    )
                # Otherwise just bail safe.
                return _response_for(202, {'status': 'accepted'})
            except Exception as e:
                # Audit table write failed — don't break webhook reception.
                # We log and fall through; signature verification still runs.
                log.exception('inbound webhook audit insert failed: %s', e)
                event = None

            # ── 3. Verify signature ──────────────────────────────────────
            try:
                verifier = get_verifier(provider)
                result = verifier.verify(request)
            except Exception as e:
                log.exception('verifier exploded: %s', e)
                _finalise(event, WebhookStatus.SIGNATURE_INVALID, 400,
                          {'error': 'invalid_signature'}, start,
                          error=f'verifier_exception: {e}')
                _safe_log_security(
                    'webhook_verifier_exception', request, 'CRITICAL',
                    {'provider': provider, 'error': str(e)[:200]},
                )
                return _response_for(400, {'error': 'invalid_signature'})

            if not result.ok:
                _finalise(event, result.fail_status, 400,
                          {'error': result.fail_status}, start)
                _safe_log_security(
                    'webhook_verification_failed', request, 'CRITICAL',
                    {'provider': provider, 'reason': result.fail_status,
                     'sig_excerpt': signature_header[:30]},
                )
                return _response_for(400, {'error': result.fail_status})

            # ── 4. Run the handler with parsed payload attached ─────────
            request._verified_webhook = {
                'provider': provider,
                'event_type': result.event_type,
                'payload': result.parsed,
                'timestamp': result.timestamp,
                'audit_event_id': getattr(event, 'id', None),
            }
            try:
                response = view_method(self, request, *args, **kwargs)
            except Exception as e:
                log.exception('webhook handler raised: %s', e)
                _finalise(event, WebhookStatus.HANDLER_FAILED, 500,
                          {'error': 'handler_failed'}, start,
                          error=f'{type(e).__name__}: {e}'[:500],
                          event_type=result.event_type)
                return _response_for(500, {'error': 'handler_failed'})

            # Normalise the response and store
            if isinstance(response, Response):
                status_code = response.status_code
                try:
                    body_data = json.loads(json.dumps(response.data, default=str))
                except Exception:
                    body_data = {}
            elif isinstance(response, HttpResponse):
                status_code = response.status_code
                try:
                    body_data = json.loads(response.content.decode('utf-8') or '{}')
                except Exception:
                    body_data = {}
            else:
                status_code, body_data = 200, response or {}

            _finalise(event, WebhookStatus.PROCESSED, status_code, body_data, start,
                      event_type=result.event_type)
            return response
        return wrapper
    return decorator


def _finalise(event, status, response_status, response_body, start, *,
              event_type='', error=''):
    """Stamp the audit row with the outcome. NEVER raises."""
    if event is None:
        return
    try:
        with transaction.atomic():
            event.status = status
            event.response_status = response_status
            try:
                event.response_body = json.dumps(response_body, default=str)[:4000]
            except Exception:
                event.response_body = str(response_body)[:4000]
            event.error = (error or '')[:1000]
            event.event_type = (event.event_type or event_type)[:80]
            event.duration_ms = int((_time.monotonic() - start) * 1000)
            event.save(update_fields=[
                'status', 'response_status', 'response_body',
                'error', 'event_type', 'duration_ms',
            ])
    except Exception:
        log.exception('finalise webhook audit failed')
