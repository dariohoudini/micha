from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class SellerVerification(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("suspended", "Suspended"),
        ("expired", "Expired"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="seller_verification")
    id_number = models.CharField(max_length=50, blank=True, null=True)
    id_document = models.FileField(upload_to="seller_ids/", blank=True, null=True)
    selfie = models.ImageField(upload_to="seller_selfies/", blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    expiry_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SellerVerification({self.user.email})"


class VerificationLog(models.Model):
    seller_verification = models.ForeignKey(SellerVerification, on_delete=models.CASCADE, related_name="logs")
    action = models.CharField(max_length=50)  # e.g., "approved", "rejected", "suspended"
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.seller_verification.user.email}"
