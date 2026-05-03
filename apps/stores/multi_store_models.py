"""
apps/stores/multi_store_models.py

Multi-store management for MICHA Express sellers.
One verified identity → multiple independent stores.
Each store has its own catalog, analytics, settings.
Seller switches between stores inside the same dashboard.

Subscription tier limits:
  Freemium    → 1 store
  Basic       → 2 stores
  Professional → 5 stores
  Enterprise  → unlimited
"""
from django.db import models
from django.conf import settings
import uuid


SUBSCRIPTION_STORE_LIMITS = {
    'freemium': 1,
    'basic': 2,
    'professional': 5,
    'enterprise': 9999,
}


class Store(models.Model):
    """
    A seller's storefront. One seller can have multiple stores.
    All stores share the same KYC verification.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='stores'
    )

    # Store identity
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    # Branding
    logo = models.ImageField(upload_to='stores/logos/', null=True, blank=True)
    banner = models.ImageField(upload_to='stores/banners/', null=True, blank=True)
    primary_color = models.CharField(max_length=7, default='#C9A84C')

    # Location
    province = models.CharField(max_length=50, default='Luanda')
    address = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)

    # Category focus
    primary_category = models.CharField(max_length=50, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(
        default=False,
        help_text="The seller's main/default store"
    )
    is_verified = models.BooleanField(default=False)

    # Policies
    return_policy = models.TextField(blank=True)
    shipping_policy = models.TextField(blank=True)

    # Stats (cached — updated by Celery)
    total_products = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    avg_rating = models.FloatField(default=0.0)
    total_reviews = models.PositiveIntegerField(default=0)
    response_rate_pct = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stores'
        ordering = ['-is_primary', 'name']
        indexes = [
            models.Index(fields=['seller', 'is_active']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return f"{self.name} ({self.seller.email})"

    @classmethod
    def can_create_store(cls, seller) -> tuple:
        """
        Returns (can_create: bool, reason: str).
        Checks subscription tier store limit.
        """
        subscription_tier = getattr(seller, 'subscription_tier', 'freemium')
        limit = SUBSCRIPTION_STORE_LIMITS.get(subscription_tier, 1)
        current_count = cls.objects.filter(seller=seller, is_active=True).count()

        if current_count >= limit:
            return False, f"O seu plano {subscription_tier} permite apenas {limit} loja(s). Actualize o plano para criar mais lojas."
        return True, ""


class StoreAnalyticsSnapshot(models.Model):
    """
    Daily analytics snapshot per store.
    Computed by Celery at midnight WAT.
    Powers the per-store analytics charts.
    """
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='analytics_snapshots')
    date = models.DateField()

    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    orders = models.PositiveIntegerField(default=0)
    products_sold = models.PositiveIntegerField(default=0)
    new_customers = models.PositiveIntegerField(default=0)
    returning_customers = models.PositiveIntegerField(default=0)
    page_views = models.PositiveIntegerField(default=0)
    wishlist_adds = models.PositiveIntegerField(default=0)
    avg_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'store_analytics_snapshots'
        unique_together = [('store', 'date')]
        ordering = ['-date']


class SellerActiveStore(models.Model):
    """
    Tracks which store a seller is currently managing.
    Updated when seller switches stores in dashboard.
    """
    seller = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='active_store_session'
    )
    active_store = models.ForeignKey(
        Store, on_delete=models.SET_NULL, null=True, blank=True
    )
    switched_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seller_active_stores'
