"""
Multicaixa Express gateway adapter.

Multicaixa Express is the dominant card+mobile payment rail in
Angola — the marketplace must accept it. Live integration uses the
EMIS Online Payment Gateway with token-based auth + push-to-phone
confirmation. Until the merchant credentials are provisioned, this
adapter is functionally complete at the protocol layer (request
shaping, signature verification) and stubs the actual HTTP call so
dev + tests pass.

When MICHA_MULTICAIXA_LIVE=True is set with real EMIS credentials,
the `_post_emis` method should be replaced with `requests.post` to
the EMIS endpoint. The rest of the adapter — request schema,
response normalisation, webhook parsing — already matches the
EMIS spec.
"""
from __future__ import annotations

import json
import logging
import secrets
from decimal import Decimal

from django.conf import settings

from .base import ChargeResult, PaymentGateway, WebhookResult

log = logging.getLogger(__name__)


class MulticaixaGateway(PaymentGateway):
    code = 'multicaixa_express'
    supports_currencies = ('AOA',)

    def __init__(self):
        self.merchant_id = getattr(settings, 'MULTICAIXA_MERCHANT_ID', 'dev-merchant')
        self.api_key = getattr(settings, 'MULTICAIXA_API_KEY', 'dev-api-key')
        self.webhook_secret = getattr(settings, 'MULTICAIXA_WEBHOOK_SECRET', 'dev-webhook-secret')
        self.live = bool(getattr(settings, 'MULTICAIXA_LIVE', False))

    def charge(self, *, amount, currency, idempotency_key, purpose,
               user_metadata, gateway_metadata) -> ChargeResult:
        if currency != 'AOA':
            return ChargeResult(
                success=False, status='failed', gateway_intent_id='',
                client_action={}, failure_code='UNSUPPORTED_CURRENCY',
                failure_message='Multicaixa accepts AOA only.',
            )
        payload = {
            'merchantId': self.merchant_id,
            'reference': idempotency_key[:20],
            'amount': str(amount),
            'currency': 'AOA',
            'description': purpose[:120],
            'phone': user_metadata.get('phone', ''),
            'callbackUrl': gateway_metadata.get('callback_url', ''),
            'returnUrl': gateway_metadata.get('return_url', ''),
        }
        try:
            response = self._post_emis('/charges', payload)
        except Exception as e:
            log.exception('multicaixa charge failed: %s', e)
            return ChargeResult(
                success=False, status='failed', gateway_intent_id='',
                client_action={},
                failure_code='GATEWAY_UNREACHABLE',
                failure_message=str(e)[:255],
            )

        # EMIS responds with either an OTP-required state (most common)
        # or an immediate success when the user is enrolled in
        # auto-debit. Normalise both into our ChargeResult.
        if response.get('status') == 'pending_user_action':
            return ChargeResult(
                success=False, status='requires_action',
                gateway_intent_id=response.get('transactionId', ''),
                client_action={
                    'kind': 'push_to_phone',
                    'message': 'Confirme o pagamento no seu telemóvel via Multicaixa Express.',
                    'reference': response.get('reference', ''),
                    'entity': response.get('entity', ''),
                    'expires_in_seconds': response.get('expiresIn', 600),
                },
                raw_response=response,
            )
        if response.get('status') == 'succeeded':
            return ChargeResult(
                success=True, status='succeeded',
                gateway_intent_id=response.get('transactionId', ''),
                client_action={}, raw_response=response,
            )
        return ChargeResult(
            success=False, status='failed',
            gateway_intent_id=response.get('transactionId', ''),
            client_action={},
            failure_code=response.get('errorCode', 'UNKNOWN'),
            failure_message=response.get('errorMessage', '')[:255],
            raw_response=response,
        )

    def refund(self, *, gateway_intent_id, amount, currency, reason) -> dict:
        try:
            return self._post_emis('/refunds', {
                'transactionId': gateway_intent_id,
                'amount': str(amount), 'currency': currency,
                'reason': reason[:120],
            })
        except Exception as e:
            log.exception('multicaixa refund failed: %s', e)
            return {'status': 'failed', 'error': str(e)[:255]}

    def verify_webhook(self, *, headers, body, body_text) -> WebhookResult:
        signature = headers.get('X-EMIS-Signature') or headers.get('HTTP_X_EMIS_SIGNATURE', '')
        expected = self._hmac_sha256(self.webhook_secret, body)
        if not _constant_time_eq(expected, signature):
            return WebhookResult(valid=False, error='SIGNATURE_MISMATCH')
        try:
            payload = json.loads(body_text)
        except Exception as e:
            return WebhookResult(valid=False, error=f'BAD_JSON: {e}')
        event_type = payload.get('event', '')
        provider_event_id = payload.get('eventId', '')
        ref = payload.get('reference', '')
        new_status = {
            'charge.succeeded': 'succeeded',
            'charge.failed':    'failed',
            'charge.cancelled': 'cancelled',
            'charge.refunded':  'refunded',
        }.get(event_type, '')
        return WebhookResult(
            valid=True, event_type=event_type,
            provider_event_id=provider_event_id, payload=payload,
            intent_id=ref, new_status=new_status,
        )

    # ── internal ────────────────────────────────────────────────

    def _post_emis(self, path: str, body: dict) -> dict:
        """In live mode this calls EMIS via `requests`. In dev/test we
        return a deterministic stub so the rest of the pipeline can be
        exercised without network."""
        if self.live:
            try:
                import requests
                r = requests.post(
                    f'https://api.emis.co.ao/v1{path}',
                    json=body,
                    headers={'Authorization': f'Bearer {self.api_key}'},
                    timeout=20,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e:
                log.exception('multicaixa live call failed: %s', e)
                raise

        # Dev stub: half the time return pending_user_action, half the
        # time succeed. Deterministic on the reference so smoke tests
        # are stable.
        ref = body.get('reference', '') or secrets.token_hex(8)
        if path == '/refunds':
            return {'status': 'succeeded', 'transactionId': f'tx_refund_{ref}'}
        if int(ref[-1:] or '0', 16) % 2 == 0:
            return {
                'status': 'pending_user_action',
                'transactionId': f'tx_{ref}',
                'reference': ref,
                'entity': '00077',
                'expiresIn': 600,
            }
        return {
            'status': 'succeeded',
            'transactionId': f'tx_{ref}',
        }


def _constant_time_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
