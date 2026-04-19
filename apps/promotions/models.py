from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Coupon(models.Model):
    TYPE_CHOICES = (
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
        ('free_shipping', 'Free Shipping'),
    )

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Cap for percentage discounts'
    )

    # Limits
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)

    # Who created it (admin or seller)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_coupons'
    )
    # Optionally restrict to a specific seller's products
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='seller_coupons'
    )

    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.discount_type})"

    def is_valid(self):
        if not self.is_active:
            return False
        if self.valid_until and timezone.now() > self.valid_until:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, subtotal):
        if subtotal < self.min_order_amount:
            return 0
        if self.discount_type == 'percentage':
            discount = subtotal * (self.discount_value / 100)
            if self.max_discount_amount:
                discount = min(discount, self.max_discount_amount)
            return round(discount, 2)
        elif self.discount_type == 'fixed':
            return min(self.discount_value, subtotal)
        elif self.discount_type == 'free_shipping':
            return 0  # handled at shipping level
        return 0


class FlashSale(models.Model):
    """Time-limited discount on a specific product."""
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='flash_sales'
    )
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_live(self):
        now = timezone.now()
        return self.is_active and self.start_time <= now <= self.end_time

    @property
    def discount_percentage(self):
        if self.original_price > 0:
            return round(((self.original_price - self.sale_price) / self.original_price) * 100, 1)
        return 0

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Flash sale: {self.product.title} — {self.sale_price}"
