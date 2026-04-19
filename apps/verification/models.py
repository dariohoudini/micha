"""
Seller Verification Models
SECURITY FIX: Angolan national ID (BI number) is encrypted at field level.
This is the most sensitive PII in the system — must never be plain text.
"""
import re
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.payments.models import EncryptedCharField

User = settings.AUTH_USER_MODEL


def validate_angolan_bi(value):
    """
    Angolan BI format: 9 digits + 2 uppercase letters + 3 digits = 14 chars
    Example: 006123456LA041
    """
    pattern = r'^\d{9}[A-Z]{2}\d{3}$'
    if not re.match(pattern, value.strip()):
        raise ValidationError(
            'Invalid Angolan BI format. Expected: 9 digits + 2 uppercase letters + 3 digits. '
            'Example: 006123456LA041'
        )


class SellerVerification(models.Model):
    STATUS = (
        ('pending', 'Pending'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    )

    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification')

    # SECURITY: Angolan national ID encrypted — plaintext never stored
    id_number = EncryptedCharField(
        max_length=500,
        validators=[validate_angolan_bi],
        help_text='Angolan BI number — stored encrypted'
    )
    id_expiry_date = models.DateField()
    id_document = models.ImageField(upload_to='verification/documents/')
    selfie = models.ImageField(upload_to='verification/selfies/')

    status = models.CharField(max_length=15, choices=STATUS, default='pending')
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verification_reviews'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def approve(self, reviewed_by):
        from django.utils import timezone
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.approved_at = timezone.now()
        self.save()
        self.seller.is_verified_seller = True
        self.seller.save(update_fields=['is_verified_seller'])

    def reject(self, reviewed_by, reason=''):
        from django.utils import timezone
        self.status = 'rejected'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def __str__(self):
        return f"Verification({self.seller.email}): {self.status}"


class VerificationLog(models.Model):
    """Audit log of every verification status change."""
    verification = models.ForeignKey(
        SellerVerification, on_delete=models.CASCADE, related_name='logs'
    )
    action = models.CharField(max_length=50)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verification_logs'
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} — {self.verification.seller.email}"
