"""
apps/notifications/whatsapp_webhook.py
───────────────────────────────────────

WhatsApp Business webhook receiver (R5).

Why this exists
───────────────
80% of high-value buyer-seller communication in Angola happens on
WhatsApp. Order confirmations, dispute messages, delivery updates
arrive in WhatsApp far more reliably than in-app push. This module
ingests Meta WhatsApp Business webhooks for:
  • Message status updates (delivered / read / failed)
  • Inbound buyer messages (route to seller chat)
  • Template messaging delivery acks

Auth
────
Meta sends a verification GET on subscription:
  GET /whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=X
                       &hub.challenge=Y
The verify_token is shared at subscription time. Settings:
  WHATSAPP_VERIFY_TOKEN  — must match the value configured at Meta.

POST verification:
  Meta signs the body with HMAC-SHA256 using the App Secret.
  Header: ``X-Hub-Signature-256: sha256=<hex>``
Settings:
  WHATSAPP_APP_SECRET  — verifies the body signature.

When WHATSAPP_VERIFY_TOKEN is unset, the endpoint refuses subscription.
When WHATSAPP_APP_SECRET is unset, POSTs are refused with 401.

This module is intentionally a STUB for the business-logic side —
inbound message routing into the existing chat models is left for
a follow-up sprint that aligns the schema. The webhook receive,
auth, and event-logging machinery IS production-ready here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


log = logging.getLogger('micha.whatsapp')


def _verify_token() -> str:
    return (getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '') or '').strip()


def _app_secret() -> bytes:
    return (getattr(settings, 'WHATSAPP_APP_SECRET', '') or '').encode('utf-8')


def _verify_signature(body: bytes, header: str) -> bool:
    secret = _app_secret()
    if not secret or not header:
        return False
    if not header.startswith('sha256='):
        return False
    expected = hmac.new(secret, body or b'', hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len('sha256='):].strip())


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def whatsapp_webhook(request):
    """Meta WhatsApp Business webhook entrypoint."""
    if request.method == 'GET':
        # Subscription verification.
        token = _verify_token()
        if not token:
            return HttpResponse('verify token not configured', status=403)
        mode = request.GET.get('hub.mode', '')
        challenge = request.GET.get('hub.challenge', '')
        sent_token = request.GET.get('hub.verify_token', '')
        if mode == 'subscribe' and hmac.compare_digest(sent_token, token):
            return HttpResponse(challenge, content_type='text/plain')
        return HttpResponse('verification failed', status=403)

    # POST: HMAC-verified event delivery.
    sig = request.META.get('HTTP_X_HUB_SIGNATURE_256', '')
    if not _verify_signature(request.body or b'', sig):
        return HttpResponse('invalid signature', status=401)

    try:
        payload = json.loads((request.body or b'').decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest('invalid json')

    # Persist minimal event log + dispatch to handlers.
    _record_event(payload)
    return HttpResponse('ok', content_type='text/plain')


def _record_event(payload: dict) -> None:
    """Best-effort event log. Specific handlers (message-status updates,
    inbound chat routing) live in a follow-up sprint that aligns the
    chat schema. For now we just log + emit an outbox event so the
    pipeline is observable.
    """
    try:
        log.info('whatsapp_webhook_event',
                 extra={'object': payload.get('object'),
                        'entry_count': len(payload.get('entry', []) or [])})
        from apps.outbox.service import publish
        publish(
            topic='notifications.whatsapp.event',
            payload={'raw': payload},
            dedupe_key=None,
            ref_type='whatsapp_event', ref_id='',
        )
    except Exception:
        log.warning('whatsapp_webhook: event recording failed',
                    exc_info=True)
