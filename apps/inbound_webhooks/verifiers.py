"""
apps/inbound_webhooks/verifiers.py

Provider-specific signature/timestamp verification. Each verifier returns a
VerifyResult that the decorator uses to decide:

  * Should we run the handler?
  * What audit status do we record?

Provider quirks are encapsulated here so the decorator stays generic.
"""
from __future__ import annotations
import hmac
import hashlib
import time
from dataclasses import dataclass
from typing import Optional

from django.conf import settings


# Replay window for timestamped signatures (Stripe-style). Anything older is
# rejected — limits the value of captured signed payloads.
DEFAULT_MAX_TIMESTAMP_AGE_SECONDS = 300  # 5 minutes


@dataclass
class VerifyResult:
    ok: bool
    fail_status: str = ''          # one of WebhookStatus values when not ok
    event_type: str = ''
    timestamp: Optional[int] = None
    parsed: Optional[dict] = None  # JSON-parsed body if we got that far


class BaseVerifier:
    """Each subclass implements ``verify(request) -> VerifyResult``.

    The decorator handles audit-row creation, replay detection, response
    caching. Verifiers should NOT do any of that themselves.
    """
    provider: str = ''

    def verify(self, request) -> VerifyResult:
        raise NotImplementedError


# ─── AppyPay (HMAC-SHA256 over body only) ─────────────────────────────────
class AppyPayVerifier(BaseVerifier):
    provider = 'appypay'
    header_name = 'HTTP_X_APPYPAY_SIGNATURE'
    timestamp_header_name = 'HTTP_X_APPYPAY_TIMESTAMP'

    def _secret(self) -> str:
        return getattr(settings, 'APPYPAY_SECRET', '') or ''

    def verify(self, request) -> VerifyResult:
        from .models import WebhookStatus

        secret = self._secret()
        if not secret:
            # Mis-configuration — refuse all. (Better to fail closed.)
            return VerifyResult(False, fail_status=WebhookStatus.SIGNATURE_INVALID,
                                event_type='', parsed=None)

        sig = request.META.get(self.header_name, '').strip()
        if not sig:
            return VerifyResult(False, fail_status=WebhookStatus.MISSING_SIGNATURE)

        body = request.body or b''
        # AppyPay docs: HMAC-SHA256(secret, body) hex-encoded.
        # If they later add a timestamp, we'll fold it in here.
        expected = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return VerifyResult(False, fail_status=WebhookStatus.SIGNATURE_INVALID)

        # Optional timestamp header — enforce if present
        ts_str = request.META.get(self.timestamp_header_name, '').strip()
        ts: Optional[int] = None
        if ts_str:
            try:
                ts = int(ts_str)
                if abs(time.time() - ts) > DEFAULT_MAX_TIMESTAMP_AGE_SECONDS:
                    return VerifyResult(False, fail_status=WebhookStatus.STALE_TIMESTAMP, timestamp=ts)
            except ValueError:
                return VerifyResult(False, fail_status=WebhookStatus.STALE_TIMESTAMP)

        # Parse the body
        try:
            import json
            parsed = json.loads(body.decode('utf-8') or '{}')
        except Exception:
            return VerifyResult(False, fail_status=WebhookStatus.MALFORMED)
        event_type = (parsed.get('event') or parsed.get('type') or '')[:80]

        return VerifyResult(True, event_type=event_type, timestamp=ts, parsed=parsed)


# ─── Stripe-style (timestamp + v1 hex over "ts.body") ─────────────────────
class StripeVerifier(BaseVerifier):
    provider = 'stripe'
    header_name = 'HTTP_STRIPE_SIGNATURE'

    def _secret(self) -> str:
        return getattr(settings, 'STRIPE_WEBHOOK_SECRET', '') or ''

    def verify(self, request) -> VerifyResult:
        from .models import WebhookStatus

        secret = self._secret()
        if not secret:
            return VerifyResult(False, fail_status=WebhookStatus.SIGNATURE_INVALID)

        header = request.META.get(self.header_name, '')
        if not header:
            return VerifyResult(False, fail_status=WebhookStatus.MISSING_SIGNATURE)

        try:
            parts = dict(p.split('=', 1) for p in header.split(','))
            ts = int(parts['t'])
            sig = parts['v1']
        except Exception:
            return VerifyResult(False, fail_status=WebhookStatus.SIGNATURE_INVALID)

        if abs(time.time() - ts) > DEFAULT_MAX_TIMESTAMP_AGE_SECONDS:
            return VerifyResult(False, fail_status=WebhookStatus.STALE_TIMESTAMP, timestamp=ts)

        body = request.body or b''
        signed = f'{ts}.'.encode('utf-8') + body
        expected = hmac.new(secret.encode('utf-8'), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return VerifyResult(False, fail_status=WebhookStatus.SIGNATURE_INVALID, timestamp=ts)

        try:
            import json
            parsed = json.loads(body.decode('utf-8') or '{}')
        except Exception:
            return VerifyResult(False, fail_status=WebhookStatus.MALFORMED, timestamp=ts)
        event_type = (parsed.get('type') or parsed.get('event') or '')[:80]

        return VerifyResult(True, event_type=event_type, timestamp=ts, parsed=parsed)


# ─── Registry — lookup by provider key ─────────────────────────────────────
_REGISTRY: dict[str, BaseVerifier] = {}


def register(verifier: BaseVerifier):
    _REGISTRY[verifier.provider] = verifier
    return verifier


def get_verifier(provider: str) -> BaseVerifier:
    if provider not in _REGISTRY:
        raise KeyError(f'No verifier registered for provider {provider!r}')
    return _REGISTRY[provider]


# Register built-ins
register(AppyPayVerifier())
register(StripeVerifier())
