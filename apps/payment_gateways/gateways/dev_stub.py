"""
Dev / test stub gateway.

Auto-succeeds every charge. Used by the membership-billing sweep
when no PSP is configured for the user's market — keeps E2E tests
fast and doesn't require network access.
"""
from __future__ import annotations

import secrets

from .base import ChargeResult, PaymentGateway, WebhookResult


class DevStubGateway(PaymentGateway):
    code = 'dev_stub'
    supports_currencies = ('*',)  # accepts anything

    def charge(self, *, amount, currency, idempotency_key, purpose,
               user_metadata, gateway_metadata) -> ChargeResult:
        return ChargeResult(
            success=True, status='succeeded',
            gateway_intent_id=f'devstub_{secrets.token_hex(6)}',
            client_action={},
            raw_response={'dev': True, 'amount': str(amount),
                          'currency': currency},
        )

    def refund(self, *, gateway_intent_id, amount, currency, reason) -> dict:
        return {'status': 'succeeded',
                'refund_id': f'devstub_re_{secrets.token_hex(6)}'}

    def verify_webhook(self, *, headers, body, body_text) -> WebhookResult:
        # Dev webhooks are trusted.
        try:
            import json
            payload = json.loads(body_text) if body_text else {}
        except Exception:
            payload = {}
        return WebhookResult(
            valid=True, event_type='dev.stub',
            provider_event_id=f'devstub_evt_{secrets.token_hex(6)}',
            payload=payload, intent_id=payload.get('intent_id', ''),
            new_status='succeeded',
        )
