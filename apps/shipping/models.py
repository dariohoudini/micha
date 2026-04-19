from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class ShippingAddress(models.Model):
    """Buyer's saved delivery addresses."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_addresses')
    label = models.CharField(max_length=50, default='Home')  # Home, Work, Other
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    address_line = models.TextField()
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, default='Angola')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def save(self, *args, **kwargs):
        # Ensure only one default address per user
        if self.is_default:
            ShippingAddress.objects.filter(
                user=self.user, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} — {self.user.email}"


class DeliveryZone(models.Model):
    """Shipping cost by city/zone. Admin configures these."""
    city = models.CharField(max_length=100, unique=True)
    province = models.CharField(max_length=100, blank=True)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_days_min = models.PositiveIntegerField(default=1)
    estimated_days_max = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['city']

    def __str__(self):
        return f"{self.city} — {self.shipping_cost} AOA"
