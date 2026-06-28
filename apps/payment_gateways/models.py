"""
Payment-gateway data model.

Two tables:

  PaymentIntent
    The merchant-side intent to take money. Owns the lifecycle from
    `created` → `requires_action` (3DS / SMS code) → `processing` →
    `succeeded` / `failed` / `cancelled`. Idempotent on
    `idempotency_key` so a retried checkout submit can't double-charge.

  GatewayTransaction
    Every wire-level message exchanged with a gateway lands here:
    creates, redirects, webhooks, refunds. Append-only — debugging
    payment incidents months later is impossible without it.

We deliberately don't store PAN / CVV / full card details. Tokens
only (gateway-side handles are kept). For Multicaixa Express the
"reference" + "entity" pair is the equivalent token.
"""
from __future__ import annotations

import secrets
import uuid

from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


GATEWAY_CHOICES = (
    ('multicaixa_express', 'Multicaixa Express (Angola)'),
    ('stripe',             'Stripe'),
    ('paypal',             'PayPal'),
    ('manual',             'Manual / Bank transfer'),
    ('dev_stub',           'Dev stub (auto-succeed)'),
)

INTENT_STATUS_CHOICES = (
    ('created',         'Created'),
    ('requires_action', 'Requires user action (3DS / OTP)'),
    ('processing',      'Processing'),
    ('succeeded',       'Succeeded'),
    ('failed',          'Failed'),
    ('cancelled',       'Cancelled'),
    ('refunded',        'Refunded'),
    ('partially_refunded', 'Partially refunded'),
)


class PaymentIntent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.CharField(max_length=24, choices=GATEWAY_CHOICES)
    # Idempotency lives at the intent level — same key from caller =
    # same intent, no double-charge.
    idempotency_key = models.CharField(max_length=80, unique=True)
    purpose = models.CharField(
        max_length=40,
        help_text='premium_billing, checkout, dispute_refund, etc.',
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payment_intents',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    status = models.CharField(
        max_length=24, choices=INTENT_STATUS_CHOICES,
        default='created', db_index=True,
    )
    gateway_intent_id = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Provider-side ID (Stripe pi_..., Multicaixa reference)',
    )
    client_action = models.JSONField(
        default=dict, blank=True,
        help_text='What the FE should do next: redirect URL, OTP prompt, etc.',
    )
    metadata = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default='')
    failure_message = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['gateway', 'status']),
            models.Index(fields=['user', '-created_at']),
        ]

    @staticmethod
    def make_idempotency_key(prefix: str = 'pi') -> str:
        return f'{prefix}_{secrets.token_urlsafe(16)}'


TXN_KIND_CHOICES = (
    ('create',   'Create'),
    ('confirm',  'Confirm'),
    ('webhook',  'Webhook callback'),
    ('refund',   'Refund'),
    ('cancel',   'Cancel'),
    ('redirect','User redirect'),
)


class GatewayTransaction(models.Model):
    """Append-only wire log. Whenever we POST to the gateway or
    receive a webhook, one row lands here."""

    id = models.BigAutoField(primary_key=True)
    intent = models.ForeignKey(
        PaymentIntent, on_delete=models.CASCADE, related_name='transactions',
    )
    kind = models.CharField(max_length=16, choices=TXN_KIND_CHOICES)
    gateway = models.CharField(max_length=24, choices=GATEWAY_CHOICES)
    direction = models.CharField(
        max_length=8,
        choices=(('outbound', 'Outbound'), ('inbound', 'Inbound')),
    )
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['occurred_at']


class GatewayWebhookEvent(models.Model):
    """Dedup for inbound webhook events. Same `provider_event_id`
    twice → second one is acknowledged but ignored to keep
    idempotency. Required by Stripe spec and good hygiene
    elsewhere."""

    id = models.BigAutoField(primary_key=True)
    gateway = models.CharField(max_length=24, choices=GATEWAY_CHOICES)
    provider_event_id = models.CharField(max_length=120, unique=True)
    event_type = models.CharField(max_length=80, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    signature_valid = models.BooleanField(default=False)
    processed_ok = models.BooleanField(default=False)
    error = models.CharField(max_length=255, blank=True, default='')
