"""
apps/inbound_webhooks/models.py

Every inbound webhook attempt — verified OR rejected — gets a row in
InboundWebhookEvent. This serves THREE purposes:

  1. Forensics. If we ever wonder "did Stripe really send us X?", the audit
     trail is here with the raw signature header, source IP, body hash.
  2. Replay protection at the storage layer. A UNIQUE constraint on
     (provider, body_sha256) means the same exact body received twice is
     automatically dropped — even if it has a valid signature and timestamp.
  3. Idempotent replay responses. When a duplicate arrives we return the
     ORIGINAL response status, not "200 again" — so a misbehaving provider
     that keeps retrying gets a consistent answer.

We intentionally store the FULL body and signature header at receipt time so
that on signature-failure we still have a complete record of the attack
attempt for incident response.
"""
import hashlib
from django.db import models


class WebhookStatus(models.TextChoices):
    RECEIVED         = 'received',         'Received (in-flight)'
    SIGNATURE_INVALID= 'signature_invalid','Rejected — bad signature'
    MISSING_SIGNATURE= 'missing_signature','Rejected — no signature header'
    REPLAY_DETECTED  = 'replay_detected',  'Rejected — duplicate body'
    STALE_TIMESTAMP  = 'stale_timestamp',  'Rejected — timestamp outside window'
    MALFORMED        = 'malformed',        'Rejected — body unparseable'
    PROCESSED        = 'processed',        'Verified + handler succeeded'
    HANDLER_FAILED   = 'handler_failed',   'Verified but handler raised'


class InboundWebhookEvent(models.Model):
    provider = models.CharField(max_length=40, db_index=True)
    # SHA-256 of the raw request body. Used for replay detection — a
    # legitimate provider should never re-send the byte-identical body.
    body_sha256 = models.CharField(max_length=64, db_index=True)
    # Truncated body for forensics (kept reasonable to bound storage).
    body_excerpt = models.TextField(blank=True)

    # Raw security headers as received — fail-state forensic value.
    signature_header = models.CharField(max_length=500, blank=True)
    timestamp_header = models.CharField(max_length=64, blank=True)

    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    status = models.CharField(
        max_length=20, choices=WebhookStatus.choices,
        default=WebhookStatus.RECEIVED, db_index=True,
    )
    # Parsed event type if signature passed (e.g. 'payment.confirmed').
    event_type = models.CharField(max_length=80, blank=True, db_index=True)
    # What HTTP status we returned — replayed verbatim if a duplicate arrives.
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.TextField(blank=True)
    error = models.TextField(blank=True)

    # Latency from receipt → response (verifies + handler total)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            # Same exact body from the same provider can only land once.
            models.UniqueConstraint(
                fields=['provider', 'body_sha256'],
                name='uniq_provider_body_hash',
            ),
        ]
        indexes = [
            models.Index(fields=['provider', '-received_at']),
            models.Index(fields=['status', '-received_at']),
        ]
        ordering = ['-received_at']

    @staticmethod
    def hash_body(body: bytes) -> str:
        return hashlib.sha256(body or b'').hexdigest()

    def __str__(self):
        return f'{self.provider} {self.event_type or self.status} @ {self.received_at:%H:%M:%S}'
