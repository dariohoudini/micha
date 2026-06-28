"""
Payment service — the only entry point callers should use.

`charge(...)`  — top-level "take money" call.  Creates the
PaymentIntent, dispatches to the right gateway, logs every wire
message, and returns a normalised result.

`handle_webhook(...)`  — entry point for inbound gateway callbacks.
Dedupes on `provider_event_id`, verifies signature, applies the new
status to the PaymentIntent, and logs.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .gateways.registry import get_gateway, select_gateway_for
from .models import (
    GatewayTransaction, GatewayWebhookEvent, PaymentIntent,
)

log = logging.getLogger(__name__)


@transaction.atomic
def charge(*, amount: Decimal, currency: str, purpose: str,
           idempotency_key: str = None, user=None,
           gateway_name: str = None, country: str = '',
           user_metadata: dict = None,
           gateway_metadata: dict = None) -> dict:
    """Idempotent on `idempotency_key`. If the key already maps to a
    PaymentIntent we return that one without making a second call to
    the gateway."""
    user_metadata = user_metadata or {}
    gateway_metadata = gateway_metadata or {}
    idempotency_key = idempotency_key or PaymentIntent.make_idempotency_key()

    existing = PaymentIntent.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return _intent_to_dict(existing)

    gw = (
        get_gateway(gateway_name)
        if gateway_name else
        select_gateway_for(currency=currency, country=country)
    )
    intent = PaymentIntent.objects.create(
        gateway=gw.code, idempotency_key=idempotency_key,
        purpose=purpose, user=user, amount=amount, currency=currency,
        status='created',
        metadata={'country': country, **(gateway_metadata or {})},
    )
    if user:
        user_metadata = {**user_metadata, 'user_id': str(user.pk)}

    GatewayTransaction.objects.create(
        intent=intent, kind='create', gateway=gw.code,
        direction='outbound',
        request_payload={'amount': str(amount), 'currency': currency,
                         'purpose': purpose},
    )
    result = gw.charge(
        amount=amount, currency=currency,
        idempotency_key=idempotency_key, purpose=purpose,
        user_metadata=user_metadata, gateway_metadata=gateway_metadata,
    )
    intent.gateway_intent_id = result.gateway_intent_id
    intent.status = result.status
    intent.client_action = result.client_action or {}
    intent.failure_code = result.failure_code or ''
    intent.failure_message = result.failure_message or ''
    if result.status in ('succeeded', 'failed', 'cancelled'):
        intent.completed_at = timezone.now()
    intent.save()

    GatewayTransaction.objects.create(
        intent=intent, kind='confirm', gateway=gw.code,
        direction='inbound',
        request_payload={}, response_payload=result.raw_response or {},
        success=result.success,
    )
    return _intent_to_dict(intent)


@transaction.atomic
def refund(*, intent_id: str, amount: Decimal = None,
           reason: str = '') -> dict:
    intent = PaymentIntent.objects.select_for_update().get(pk=intent_id)
    if intent.status != 'succeeded':
        return {'ok': False, 'reason': 'INTENT_NOT_SUCCEEDED'}
    gw = get_gateway(intent.gateway)
    amt = amount or intent.amount
    GatewayTransaction.objects.create(
        intent=intent, kind='refund', gateway=gw.code,
        direction='outbound',
        request_payload={'amount': str(amt), 'reason': reason},
    )
    resp = gw.refund(
        gateway_intent_id=intent.gateway_intent_id,
        amount=amt, currency=intent.currency, reason=reason,
    )
    success = resp.get('status') == 'succeeded'
    if success:
        intent.status = 'refunded' if amt == intent.amount else 'partially_refunded'
        intent.save(update_fields=['status', 'updated_at'])
    GatewayTransaction.objects.create(
        intent=intent, kind='refund', gateway=gw.code,
        direction='inbound', response_payload=resp, success=success,
    )
    return {'ok': success, 'gateway_response': resp,
            'new_status': intent.status}


@transaction.atomic
def handle_webhook(*, gateway_name: str, headers: dict, body: bytes,
                    body_text: str = '') -> dict:
    """Generic webhook entry point. Routes to the gateway's
    `verify_webhook` then applies the status update."""
    gw = get_gateway(gateway_name)
    result = gw.verify_webhook(
        headers=headers, body=body, body_text=body_text or body.decode('utf-8', errors='replace'),
    )
    if not result.valid:
        # Persist the failed-validation row so we can replay/inspect.
        GatewayWebhookEvent.objects.create(
            gateway=gw.code,
            provider_event_id=result.provider_event_id or f'invalid_{timezone.now().timestamp()}',
            event_type=result.event_type or 'invalid',
            payload=result.payload or {},
            signature_valid=False, processed_ok=False,
            error=result.error[:255],
        )
        return {'ok': False, 'error': result.error}

    # Dedup.
    obj, created = GatewayWebhookEvent.objects.get_or_create(
        provider_event_id=result.provider_event_id,
        defaults={
            'gateway': gw.code, 'event_type': result.event_type,
            'payload': result.payload or {}, 'signature_valid': True,
        },
    )
    if not created:
        return {'ok': True, 'duplicate': True,
                'event_id': obj.provider_event_id}

    # Apply new status if we have a known intent.
    intent = PaymentIntent.objects.filter(
        gateway_intent_id=result.intent_id,
    ).first() if result.intent_id else None
    if intent and result.new_status:
        prev = intent.status
        intent.status = result.new_status
        if result.new_status in ('succeeded', 'failed', 'cancelled', 'refunded'):
            intent.completed_at = timezone.now()
        intent.save(update_fields=['status', 'completed_at', 'updated_at'])
        GatewayTransaction.objects.create(
            intent=intent, kind='webhook', gateway=gw.code,
            direction='inbound', response_payload=result.payload or {},
            success=result.new_status == 'succeeded',
        )
        log.info('payment_intent %s: %s → %s via webhook',
                 intent.id, prev, result.new_status)
    obj.processed_ok = True
    obj.processed_at = timezone.now()
    obj.save(update_fields=['processed_ok', 'processed_at'])
    return {'ok': True, 'event_id': obj.provider_event_id,
            'event_type': result.event_type}


def _intent_to_dict(intent: PaymentIntent) -> dict:
    return {
        'intent_id': str(intent.id),
        'gateway': intent.gateway,
        'status': intent.status,
        'gateway_intent_id': intent.gateway_intent_id,
        'client_action': intent.client_action,
        'failure_code': intent.failure_code,
        'failure_message': intent.failure_message,
        'amount': str(intent.amount), 'currency': intent.currency,
    }
