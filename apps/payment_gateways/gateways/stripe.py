"""
Stripe gateway adapter.

Targets the modern Payment Intents + Setup Intents API. Live mode
requires `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`. Dev/test
mode skips the network call and returns a deterministic stub — the
rest of the pipeline (idempotency, status mapping, webhook dedup) is
unchanged so it can be exercised without keys.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from decimal import Decimal

from django.conf import settings

from .base import ChargeResult, PaymentGateway, WebhookResult

log = logging.getLogger(__name__)


class StripeGateway(PaymentGateway):
    code = 'stripe'
    supports_currencies = ('USD', 'EUR', 'GBP', 'BRL')

    def __init__(self):
        self.api_key = getattr(settings, 'STRIPE_SECRET_KEY', 'sk_test_dev')
        self.webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', 'whsec_dev')
        self.live = bool(getattr(settings, 'STRIPE_LIVE', False))

    def charge(self, *, amount, currency, idempotency_key, purpose,
               user_metadata, gateway_metadata) -> ChargeResult:
        currency = currency.upper()
        if currency not in self.supports_currencies:
            return ChargeResult(
                success=False, status='failed', gateway_intent_id='',
                client_action={},
                failure_code='UNSUPPORTED_CURRENCY',
                failure_message=f'Stripe doesn\'t support {currency} in MICHA config.',
            )
        # Stripe takes minor units (cents).
        amount_minor = int((Decimal(amount) * 100).to_integral_value())
        payment_method = gateway_metadata.get('payment_method_id', '')
        try:
            response = self._create_intent({
                'amount': amount_minor, 'currency': currency.lower(),
                'description': purpose[:120],
                'payment_method': payment_method,
                'confirm': bool(payment_method),
                'metadata': {
                    'purpose': purpose,
                    'user_id': user_metadata.get('user_id', ''),
                },
            }, idempotency_key=idempotency_key)
        except Exception as e:
            log.exception('stripe charge failed: %s', e)
            return ChargeResult(
                success=False, status='failed', gateway_intent_id='',
                client_action={},
                failure_code='GATEWAY_UNREACHABLE',
                failure_message=str(e)[:255],
            )

        intent_id = response.get('id', '')
        status_map = {
            'requires_payment_method': ('failed',          'PAYMENT_METHOD_REQUIRED'),
            'requires_confirmation':   ('requires_action', ''),
            'requires_action':         ('requires_action', ''),
            'processing':              ('processing',      ''),
            'requires_capture':        ('processing',      ''),
            'succeeded':               ('succeeded',       ''),
            'canceled':                ('cancelled',       ''),
        }
        stripe_status = response.get('status', 'failed')
        our_status, default_failure = status_map.get(
            stripe_status, ('failed', stripe_status),
        )
        client_action = {}
        if our_status == 'requires_action':
            client_action = {
                'kind': '3ds_redirect',
                'next_action': response.get('next_action') or {},
                'client_secret': response.get('client_secret', ''),
            }
        return ChargeResult(
            success=our_status == 'succeeded',
            status=our_status,
            gateway_intent_id=intent_id,
            client_action=client_action,
            failure_code='' if our_status != 'failed' else default_failure,
            failure_message=response.get('last_payment_error', {}).get('message', ''),
            raw_response=response,
        )

    def refund(self, *, gateway_intent_id, amount, currency, reason) -> dict:
        try:
            return self._call_api('POST', '/refunds', {
                'payment_intent': gateway_intent_id,
                'amount': int(Decimal(amount) * 100),
                'reason': reason[:80] or 'requested_by_customer',
            })
        except Exception as e:
            log.exception('stripe refund failed: %s', e)
            return {'status': 'failed', 'error': str(e)[:255]}

    def verify_webhook(self, *, headers, body, body_text) -> WebhookResult:
        sig = headers.get('Stripe-Signature') or headers.get('HTTP_STRIPE_SIGNATURE', '')
        if not self._verify_stripe_signature(body, sig):
            return WebhookResult(valid=False, error='SIGNATURE_MISMATCH')
        try:
            payload = json.loads(body_text)
        except Exception as e:
            return WebhookResult(valid=False, error=f'BAD_JSON: {e}')
        event_type = payload.get('type', '')
        provider_event_id = payload.get('id', '')
        data = payload.get('data', {}).get('object', {})
        intent_id = data.get('metadata', {}).get('internal_intent_id', '') or data.get('id', '')
        new_status_map = {
            'payment_intent.succeeded':         'succeeded',
            'payment_intent.payment_failed':    'failed',
            'payment_intent.canceled':          'cancelled',
            'charge.refunded':                  'refunded',
            'charge.dispute.created':           'failed',
        }
        return WebhookResult(
            valid=True, event_type=event_type,
            provider_event_id=provider_event_id, payload=payload,
            intent_id=intent_id,
            new_status=new_status_map.get(event_type, ''),
        )

    # ── internal ────────────────────────────────────────────────

    def _create_intent(self, body, *, idempotency_key):
        return self._call_api(
            'POST', '/payment_intents', body,
            idempotency_key=idempotency_key,
        )

    def _call_api(self, method, path, body, *, idempotency_key=None):
        if self.live:
            try:
                import requests
                headers = {'Authorization': f'Bearer {self.api_key}'}
                if idempotency_key:
                    headers['Idempotency-Key'] = idempotency_key
                r = requests.request(
                    method, f'https://api.stripe.com/v1{path}',
                    data=body, headers=headers, timeout=20,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e:
                log.exception('stripe live call failed: %s', e)
                raise

        # Dev stub — deterministic but variable so the FSM exercises
        # all branches.
        intent_id = f'pi_dev_{secrets.token_hex(6)}'
        if path == '/refunds':
            return {'status': 'succeeded', 'id': f're_dev_{secrets.token_hex(6)}'}
        # Half pass instantly, half require 3DS.
        if int(idempotency_key[-1:] if idempotency_key else '0', 16) % 2 == 0:
            return {
                'id': intent_id, 'status': 'requires_action',
                'client_secret': f'{intent_id}_secret_dev',
                'next_action': {
                    'type': 'redirect_to_url',
                    'redirect_to_url': {
                        'url': f'https://hooks.stripe.com/dev/3ds/{intent_id}',
                    },
                },
            }
        return {
            'id': intent_id, 'status': 'succeeded',
            'amount': body.get('amount', 0),
        }

    def _verify_stripe_signature(self, body: bytes, sig_header: str) -> bool:
        """Stripe's signature format: `t=<ts>,v1=<sig>,v1=<sig2>`."""
        if not sig_header or not body:
            # Allow in dev mode if no real key is set.
            return not self.live
        try:
            pairs = dict(p.split('=', 1) for p in sig_header.split(',') if '=' in p)
            ts = pairs.get('t', '')
            sig = pairs.get('v1', '')
            signed = f'{ts}.{body.decode("utf-8")}'.encode('utf-8')
            expected = self._hmac_sha256(self.webhook_secret, signed)
            if not _constant_time_eq(expected, sig):
                return False
            # Reject replays older than 5 min.
            if abs(int(time.time()) - int(ts)) > 300:
                return False
            return True
        except Exception:
            return False


def _constant_time_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
