"""
Abstract `PaymentGateway` interface.

Every concrete gateway (Multicaixa, Stripe, PayPal, ...) implements
this small contract. The rest of MICHA only talks to the registry
(via `get_gateway(name)`), never directly to a provider — so swapping
out a provider for a market or A/B-testing two PSPs is a config flip,
not a code edit.
"""
from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ChargeResult:
    """Normalised outcome of a charge attempt across all gateways."""
    success: bool
    status: str                       # one of PaymentIntent.status values
    gateway_intent_id: str            # provider-side reference
    client_action: dict               # redirect URL, OTP prompt, etc.
    failure_code: str = ''
    failure_message: str = ''
    raw_response: dict = None


@dataclass
class WebhookResult:
    valid: bool
    event_type: str = ''
    provider_event_id: str = ''
    payload: dict = None
    intent_id: str = ''               # our internal PaymentIntent.id (if mapped)
    new_status: str = ''              # outcome to apply to the intent
    error: str = ''


class PaymentGateway(ABC):
    """Concrete subclasses live in this package next to this file.

    The interface is intentionally narrow — `charge`, `refund`,
    `verify_webhook` is all the rest of MICHA needs to know."""

    code = 'abstract'  # override in subclasses
    supports_currencies: tuple = ()

    @abstractmethod
    def charge(
        self, *, amount: Decimal, currency: str,
        idempotency_key: str, purpose: str,
        user_metadata: dict, gateway_metadata: dict,
    ) -> ChargeResult:
        """Initiate a charge. Returns a `ChargeResult` with whatever
        next step the gateway requires (redirect URL, OTP prompt) or
        an immediate success/failure for instant-charge providers."""

    @abstractmethod
    def refund(
        self, *, gateway_intent_id: str, amount: Decimal,
        currency: str, reason: str,
    ) -> dict:
        ...

    @abstractmethod
    def verify_webhook(
        self, *, headers: dict, body: bytes, body_text: str,
    ) -> WebhookResult:
        """Verify the inbound signature + parse the event. Returns
        `WebhookResult` — caller dispatches based on `event_type`."""

    @staticmethod
    def _hmac_sha256(secret: str, body: bytes) -> str:
        return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
