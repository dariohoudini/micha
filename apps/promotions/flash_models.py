
from django.db import models
from django.conf import settings
from django.utils import timezone
User = settings.AUTH_USER_MODEL

class FlashSale(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flash_sales')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='flash_sales')
    discount_percent = models.PositiveIntegerField()
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_live(self):
        now = timezone.now()
        return self.is_active and self.starts_at <= now <= self.ends_at

    @property
    def seconds_remaining(self):
        now = timezone.now()
        if now > self.ends_at:
            return 0
        return int((self.ends_at - now).total_seconds())

    def save(self, *args, **kwargs):
        self.sale_price = self.original_price * (1 - self.discount_percent / 100)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"FlashSale {self.product.title} -{self.discount_percent}%"
