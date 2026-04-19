
from django.db import models
from django.conf import settings
User = settings.AUTH_USER_MODEL

BANNED_KEYWORDS = ["scam","fraud","fake","counterfeit","stolen","drugs","weapons"]

class ContentFlag(models.Model):
    TARGET_CHOICES = [("product","Product"),("review","Review"),("message","Message"),("listing","Listing")]
    flagger = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="content_flags")
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES)
    target_id = models.PositiveIntegerField()
    reason = models.TextField()
    auto_flagged = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]
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

class BuyerProtectionClaim(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="buyer_protection")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=[("pending","Pending"),("approved","Approved"),("rejected","Rejected")], default="pending")
    auto_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
