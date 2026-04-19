from django.db import models
from django.conf import settings
import uuid

User = settings.AUTH_USER_MODEL


class Listing(models.Model):
    """
    A general listing posted by any authenticated user.
    Simpler than a Product (no store required).
    """
    SALE_TYPE_CHOICES = (
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
        ('free', 'Free / Give Away'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sale_type = models.CharField(max_length=10, choices=SALE_TYPE_CHOICES, default='sale')
    city = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='listings/images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
