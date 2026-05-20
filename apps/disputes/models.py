
import os
from django.core.exceptions import ValidationError

def validate_attachment(file):
    allowed = ['.jpg', '.jpeg', '.png', '.pdf', '.mp4', '.mov']
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in allowed:
        raise ValidationError(f'File type not allowed. Allowed: {chr(44).join(allowed)}')
    if file.size > 10 * 1024 * 1024:
        raise ValidationError('File too large. Maximum 10MB.')


from django.db import models
from django.conf import settings
import uuid
User = settings.AUTH_USER_MODEL

class Dispute(models.Model):
    STATUS = [("open","Open"),("under_review","Under Review"),("resolved","Resolved"),("closed","Closed")]
    REASONS = [("not_received","Not received"),("not_as_described","Not as described"),("damaged","Damaged"),("fake","Fake"),("seller_unresponsive","Seller unresponsive"),("other","Other")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="dispute")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="disputes_raised")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="disputes_received")
    reason = models.CharField(max_length=30, choices=REASONS)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="open")
    admin_note = models.TextField(blank=True, null=True)
    resolution = models.CharField(max_length=20, choices=[("refund_buyer","Refund Buyer"),("pay_seller","Pay Seller"),("partial_refund","Partial Refund"),("dismissed","Dismissed")], blank=True, null=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── SLA fields ────────────────────────────────────────────────────
    # `respond_by` — seller must post a message by this time, else the
    # dispute auto-escalates. Default is 72h post-open.
    # `auto_resolve_at` — if the seller is still silent past this time,
    # the SLA sweep auto-resolves to refund_buyer. Default is 7d post-open.
    # Both are populated at open-time by disputes.service.open_dispute().
    respond_by = models.DateTimeField(null=True, blank=True)
    auto_resolve_at = models.DateTimeField(null=True, blank=True)
    last_seller_message_at = models.DateTimeField(null=True, blank=True)

    # ── Evidence snapshot ─────────────────────────────────────────────
    # Frozen at open-time so even if the product page is later edited /
    # archived, the dispute reflects what the buyer actually saw.
    # Contents: order total, item list with titles/prices/qtys, status
    # timeline (placed/shipped/delivered timestamps), product images.
    # NOT a substitute for chat history — DisputeMessage rows are the
    # authoritative back-and-forth and are immutable in practice.
    evidence_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # SLA sweep queries: WHERE status='open' AND auto_resolve_at <= now
            models.Index(fields=["status", "auto_resolve_at"]),
        ]

class DisputeMessage(models.Model):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    attachment = models.FileField(upload_to="dispute_attachments/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["created_at"]

class FraudFlag(models.Model):
    REASONS = [("suspicious_order","Suspicious order"),("high_value_new_account","High value new account"),("multiple_failed_payments","Multiple failed payments"),("unusual_location","Unusual location")]
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, null=True, blank=True, related_name="fraud_flags")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fraud_flags")
    reason = models.CharField(max_length=50, choices=REASONS)
    details = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]
