from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class ShippingTemplate(models.Model):
    """AliExpress §14.1 — seller-managed reusable shipping rule set.

    One seller can own many templates; each product can pick a
    template at create time. Methods (carrier × destination × cost
    rules) hang off ``ShippingMethod`` via FK.
    """
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_templates', db_index=True)
    name = models.CharField(max_length=80)  # seller-facing label
    ship_from_country = models.CharField(max_length=80, default='Angola')
    processing_days = models.PositiveIntegerField(default=2)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        indexes = [models.Index(fields=['seller', 'is_default'])]
        unique_together = ('seller', 'name')

    def save(self, *args, **kwargs):
        if self.is_default:
            ShippingTemplate.objects.filter(seller=self.seller, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.seller_id})"


class ShippingMethod(models.Model):
    """A single carrier × destination × cost row inside a template."""
    SERVICE_CHOICES = (
        ('standard',  'Standard'),
        ('express',   'Express'),
        ('economy',   'Economy'),
        ('dhl',       'DHL'),
        ('fedex',     'FedEx'),
        ('ups',       'UPS'),
        ('local_post','Local Post'),
        ('custom',    'Custom'),
    )
    template = models.ForeignKey(ShippingTemplate, on_delete=models.CASCADE, related_name='methods')
    service = models.CharField(max_length=20, choices=SERVICE_CHOICES, default='standard')
    custom_service_name = models.CharField(max_length=80, blank=True)
    # JSON list of country/province slugs, or ['WORLDWIDE']
    destinations = models.JSONField(default=list)
    min_days = models.PositiveIntegerField(default=1)
    max_days = models.PositiveIntegerField(default=7)
    free_shipping = models.BooleanField(default=False)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    additional_item_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordering', 'id']

    def __str__(self):
        return f"{self.template.name} → {self.get_service_display()}"


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
