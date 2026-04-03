from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class SellerVerification(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification')

    id_number = models.CharField(max_length=50)
    id_expiry_date = models.DateField()

    id_document = models.ImageField(upload_to='verification/id_documents/')
    selfie = models.ImageField(upload_to='verification/selfies/')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    last_selfie_update = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_id_valid(self):
        # Placeholder for Angolan ID validation logic
        return True

    def is_expired(self):
        return self.id_expiry_date < timezone.now().date()

    def __str__(self):
        return f"{self.user} - {self.status}"
