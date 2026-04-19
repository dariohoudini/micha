"""
Collections — admin curated content.
Covers gaps: curated collections, product of the day, seller spotlight,
platform announcements, price history chart.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class ProductCollection(models.Model):
    """Admin-curated product list — 'Back to school', 'Summer deals' etc."""
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    banner_image = models.ImageField(upload_to='collections/', blank=True, null=True)
    products = models.ManyToManyField(
        'products.Product', blank=True, related_name='collections'
    )
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def __str__(self):
        return self.name


class ProductOfTheDay(models.Model):
    """Admin picks one product to spotlight per day."""
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='featured_days'
    )
    date = models.DateField(unique=True, default=timezone.now)
    headline = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.date}: {self.product.title}"


class SellerSpotlight(models.Model):
    """Feature a verified seller on the homepage."""
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='spotlights')
    headline = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Spotlight: {self.seller.email}"


class PlatformAnnouncement(models.Model):
    """Global banner messages — maintenance, promos, new features."""
    TYPE_CHOICES = (
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('success', 'Success'),
        ('promo', 'Promo'),
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='info')
    cta_text = models.CharField(max_length=50, blank=True)
    cta_link = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    show_from = models.DateTimeField(default=timezone.now)
    show_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_live(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.show_until and now > self.show_until:
            return False
        return True

    def __str__(self):
        return self.title


class PriceHistory(models.Model):
    """
    Daily price snapshot for every active product.
    Powers the price history chart on product detail pages.
    Celery records this at midnight every day.
    """
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='price_history'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f"{self.product.title} — {self.price} @ {self.recorded_at.date()}"
