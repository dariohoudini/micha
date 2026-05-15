"""
apps/webhooks/models.py

Outbound webhook delivery to seller systems.

Composition with existing primitives:
  - Subscribes to the outbox: a fanout handler per broadcastable topic enqueues
    a WebhookDelivery row for each matching active SellerWebhook.
  - Delivery worker runs separately (Celery task) so HTTP latency to a slow
    seller never blocks the outbox dispatcher.
  - Signed with HMAC-SHA256 (Stripe-style "t=<ts>,v1=<sig>") so the receiver
    can verify authenticity AND replay-protect with the timestamp window.
  - Auto-disabled after N consecutive failures so a permanently broken seller
    URL doesn't keep filling the queue.
"""
import hmac
import hashlib
import secrets
import json
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# Topics a seller can subscribe to. Edit here when new ones are added.
ALLOWED_TOPICS = [
    'order.placed',
    'order.payment_confirmed',
    'order.shipped',
    'order.delivery_confirmed',
    'order.cancelled',
    'return.created',
    'return.approved',
    'return.completed',
    'payout.completed',
]


class SellerWebhook(models.Model):
    """A seller's registered HTTP endpoint for receiving event pushes."""
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='webhooks',
    )
    url = models.URLField(max_length=500)
    # Shared secret used to sign payloads. Generated server-side; shown to the
    # seller once at creation and never again.
    secret = models.CharField(max_length=64)
    # List of subscribed topics from ALLOWED_TOPICS. Empty list = subscribe to
    # nothing (effectively inactive).
    topics = models.JSONField(default=list)

    is_active = models.BooleanField(default=True)
    # When this hits the threshold (e.g. 10) the webhook is auto-disabled and
    # surfaces in the ops queue for human attention.
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    AUTO_DISABLE_FAILURE_THRESHOLD = 10

    class Meta:
        indexes = [
            models.Index(fields=['seller', 'is_active']),
        ]

    @classmethod
    def gen_secret(cls):
        """32 random bytes hex-encoded — 64 chars, ~256 bits of entropy."""
        return secrets.token_hex(32)

    def record_success(self):
        self.consecutive_failures = 0
        self.last_success_at = timezone.now()
        self.save(update_fields=['consecutive_failures', 'last_success_at', 'updated_at'])

    def record_failure(self):
        self.consecutive_failures += 1
        self.last_failure_at = timezone.now()
        updates = ['consecutive_failures', 'last_failure_at', 'updated_at']
        if self.consecutive_failures >= self.AUTO_DISABLE_FAILURE_THRESHOLD and self.is_active:
            self.is_active = False
            updates.append('is_active')
        self.save(update_fields=updates)


class DeliveryStatus(models.TextChoices):
    PENDING   = 'pending',   'Pending'
    DELIVERED = 'delivered', 'Delivered'
    RETRYING  = 'retrying',  'Retrying'
    DEAD      = 'dead',      'Dead (max attempts)'


class WebhookDelivery(models.Model):
    """One attempt-chain to deliver a single event to a single webhook."""
    webhook = models.ForeignKey(
        SellerWebhook, on_delete=models.CASCADE,
        related_name='deliveries',
    )
    topic = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict)
    # Dedupe: same outbox event delivered to same webhook produces the same key.
    # Lets us safely retry from the outbox without duplicating downstream pushes.
    dedupe_key = models.CharField(max_length=200, unique=True)

    status = models.CharField(
        max_length=12, choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING, db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=8)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Last HTTP response captured (for debugging / admin display)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)  # truncated
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'next_attempt_at']),
            models.Index(fields=['webhook', '-created_at']),
        ]
        ordering = ['-created_at']


# ─── Signing ────────────────────────────────────────────────────────────────
SIGNATURE_HEADER = 'X-Micha-Signature'
SIGNATURE_VERSION = 'v1'


def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    """Return a signature header value:  t=<ts>,v1=<hex>

    The signed string is "<ts>.<body>" — the timestamp inclusion is what
    prevents replay attacks (receiver rejects timestamps older than a few min).
    """
    msg = f'{timestamp}.'.encode('utf-8') + body
    digest = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()
    return f't={timestamp},{SIGNATURE_VERSION}={digest}'


def verify_signature(secret: str, header: str, body: bytes, *, max_age_seconds: int = 300) -> bool:
    """Verify a signature header. Convenience for seller-side SDKs (and our
    own internal tests). Constant-time compare; rejects stale timestamps."""
    try:
        parts = dict(p.split('=', 1) for p in header.split(','))
        ts = int(parts['t'])
        sig = parts[SIGNATURE_VERSION]
    except Exception:
        return False
    now = int(timezone.now().timestamp())
    if abs(now - ts) > max_age_seconds:
        return False
    expected = sign_payload(secret, ts, body).split(f'{SIGNATURE_VERSION}=')[1]
    return hmac.compare_digest(expected, sig)


def canonical_payload(payload) -> bytes:
    """Stable JSON serialization for signing — sorted keys, compact separators."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
