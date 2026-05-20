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


# ─── AppyPay (HMAC-SHA256) ────────────────────────────────────────────────
class AppyPayVerifier(BaseVerifier):
    """AppyPay webhook signature verification.

    Two modes governed by ``settings.APPYPAY_REQUIRE_TIMESTAMP``:

      • False (default, back-compat): HMAC-SHA256 over body only. A
        timestamp header is OPTIONAL; if present, freshness is enforced
        but the timestamp is NOT bound into the signature.

      • True (strong): timestamp header REQUIRED. Signature is computed
        over ``"<ts>.<body>"`` (Stripe-style binding). An attacker who
        captures a leaked secret only has a 5-minute window to forge
        signatures; outside that window the freshness check rejects.

    Operators flip the strong flag once AppyPay's signing implementation
    supports timestamp binding. Until then we ship back-compat behaviour
    so the integration keeps working.

    Why this matters
    ────────────────
    The HMAC-over-body-only mode is replay-safe at OUR layer (the
    decorator dedupes by body_sha256), but provides no defence if the
    signing secret leaks. Stripe-style timestamp binding bounds the
    blast radius to the freshness window.
    """
    provider = 'appypay'
    header_name = 'HTTP_X_APPYPAY_SIGNATURE'
    timestamp_header_name = 'HTTP_X_APPYPAY_TIMESTAMP'

    def _secret(self) -> str:
        return getattr(settings, 'APPYPAY_SECRET', '') or ''

    def _require_timestamp(self) -> bool:
        return bool(getattr(settings, 'APPYPAY_REQUIRE_TIMESTAMP', False))

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
        require_ts = self._require_timestamp()

        # Timestamp parse + freshness — required in strong mode.
        ts_str = request.META.get(self.timestamp_header_name, '').strip()
        ts: Optional[int] = None
        if ts_str:
            try:
                ts = int(ts_str)
            except ValueError:
                return VerifyResult(False, fail_status=WebhookStatus.STALE_TIMESTAMP)
            if abs(time.time() - ts) > DEFAULT_MAX_TIMESTAMP_AGE_SECONDS:
                return VerifyResult(False, fail_status=WebhookStatus.STALE_TIMESTAMP, timestamp=ts)
        elif require_ts:
            # Strong mode demands a timestamp; absence == missing signature
            # component, not "stale timestamp" — be honest about the cause.
            return VerifyResult(False, fail_status=WebhookStatus.MISSING_SIGNATURE)

        # Compute expected signature. Strong mode binds the timestamp
        # into the HMAC input so an attacker who captures a leaked
        # secret can't forge signatures outside the freshness window.
        if require_ts and ts is not None:
            signed_input = f'{ts}.'.encode('utf-8') + body
        else:
            signed_input = body
        expected = hmac.new(secret.encode('utf-8'), signed_input, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return VerifyResult(False, fail_status=WebhookStatus.SIGNATURE_INVALID, timestamp=ts)

        # Parse the body
        try:
            import json
            parsed = json.loads(body.decode('utf-8') or '{}')
        except Exception:
            return VerifyResult(False, fail_status=WebhookStatus.MALFORMED, timestamp=ts)
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
