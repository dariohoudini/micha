
from django.db import models
from django.conf import settings
User = settings.AUTH_USER_MODEL

BANNED_KEYWORDS = ["scam","fraud","fake","counterfeit","stolen","drugs","weapons"]

class ContentFlag(models.Model):
    TARGET_CHOICES = [("product","Product"),("review","Review"),("message","Message"),("listing","Listing")]

    # Queue-state machine (R4). ``is_resolved`` is the legacy boolean —
    # kept for backwards compat with the old admin view; ``status`` is
    # the canonical state for the moderator queue.
    STATUS_CHOICES = [
        ("pending",   "Pending"),    # waiting for moderator
        ("approved",  "Approved"),   # content reviewed and OK
        ("rejected",  "Rejected"),   # content removed, counts toward escalation
        ("escalated", "Escalated"),  # kicked to senior mod / dispute
    ]
    SEVERITY_CHOICES = [
        ("low",    "Low"),
        ("medium", "Medium"),
        ("high",   "High"),
    ]

    flagger = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="content_flags")
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES)
    target_id = models.PositiveIntegerField()
    # Owner of the flagged content — set when known. Required for the
    # escalation engine which counts rejections per user. Nullable
    # because chat messages and legacy rows may lack this linkage.
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="content_flags_against",
        help_text="Owner of the flagged content. Used by escalation engine.",
    )
    reason = models.TextField()
    auto_flagged = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)

    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default="medium",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="pending",
        db_index=True,
    )
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="content_flags_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["target_user", "status"]),
        ]

    @classmethod
    def check_content(cls, text, target_type, target_id):
        tl = text.lower()
        triggered = [kw for kw in BANNED_KEYWORDS if kw in tl]
        if triggered:
            cls.objects.create(target_type=target_type,target_id=target_id,reason=f"Auto-flagged: {','.join(triggered)}",auto_flagged=True)
            return True
        return False

class IPBan(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    reason = models.TextField()
    banned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="ip_bans_created")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

# R4: brand protection registry — re-export so Django picks up model.
from .brand_registry import ProtectedBrand  # noqa: F401,E402


class BuyerProtectionClaim(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="buyer_protection")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=[("pending","Pending"),("approved","Approved"),("rejected","Rejected")], default="pending")
    auto_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
