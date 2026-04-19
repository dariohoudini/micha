"""
Recommendation Engine Models — With DB Indexes
"""
from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class UserInterest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interests")
    category = models.ForeignKey("products.Category", on_delete=models.CASCADE, related_name="interested_users")
    score = models.FloatField(default=0.0)
    view_count = models.PositiveIntegerField(default=0)
    search_count = models.PositiveIntegerField(default=0)
    wishlist_count = models.PositiveIntegerField(default=0)
    purchase_count = models.PositiveIntegerField(default=0)
    last_interaction = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "category")
        ordering = ["-score"]
        indexes = [
            models.Index(fields=["user", "-score"]),
            models.Index(fields=["category"]),
        ]

    def recalculate_score(self):
        self.score = (
            self.view_count * 1.0 +
            self.search_count * 2.0 +
            self.wishlist_count * 3.0 +
            self.purchase_count * 10.0
        )
        self.save(update_fields=["score"])

    @classmethod
    def track(cls, user, product, interaction_type):
        if not user or not user.is_authenticated or not product.category_id:
            return
        interest, _ = cls.objects.get_or_create(user=user, category_id=product.category_id)
        field_map = {
            "view": "view_count", "cart": "view_count",
            "share": "view_count", "review": "view_count",
            "wishlist": "wishlist_count", "purchase": "purchase_count",
        }
        field = field_map.get(interaction_type, "view_count")
        from django.db.models import F
        cls.objects.filter(pk=interest.pk).update(**{field: F(field) + 1})
        interest.refresh_from_db()
        interest.recalculate_score()


class ProductInteraction(models.Model):
    TYPES = (
        ("view", "View"), ("wishlist", "Wishlist"), ("cart", "Cart"),
        ("purchase", "Purchase"), ("review", "Review"), ("share", "Share"),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="product_interactions")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="interactions")
    type = models.CharField(max_length=10, choices=TYPES)
    weight = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "type"]),
            models.Index(fields=["product", "type"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    @classmethod
    def track(cls, user, product, interaction_type):
        WEIGHTS = {"view": 1, "share": 2, "wishlist": 3, "review": 5, "cart": 5, "purchase": 10}
        if user and user.is_authenticated:
            obj = cls.objects.create(
                user=user, product=product, type=interaction_type,
                weight=WEIGHTS.get(interaction_type, 1),
            )
            UserInterest.track(user, product, interaction_type)
            return obj


class ProductSimilarity(models.Model):
    product_a = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="similar_to")
    product_b = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="similar_from")
    similarity_score = models.FloatField(default=0.0)
    co_purchase_count = models.PositiveIntegerField(default=0)
    co_view_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product_a", "product_b")
        ordering = ["-similarity_score"]
        indexes = [models.Index(fields=["product_a", "-similarity_score"])]


class PriceAlert(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="price_alerts")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="price_alerts")
    target_price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_triggered = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        indexes = [models.Index(fields=["is_triggered", "product"])]


class BackInStockAlert(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="back_in_stock_alerts")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="back_in_stock_alerts")
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        indexes = [models.Index(fields=["notified", "product"])]


class StockUrgencySignal(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="urgency_views")
    session_key = models.CharField(max_length=100)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "session_key")
        indexes = [models.Index(fields=["product", "last_seen"])]


class BrowsingSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="browsing_sessions")
    session_key = models.CharField(max_length=100, blank=True)
    products_viewed = models.ManyToManyField("products.Product", blank=True, related_name="viewed_in_sessions")
    started_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-last_active"])]
