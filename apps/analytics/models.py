"""
Analytics Models
FIX: FunnelEvent stores pseudonymous hash of user_id — not raw user_id
     Analysts cannot reconstruct individual browsing history from hash
"""
import hashlib
from django.db import models
from django.conf import settings
from decimal import Decimal

User = settings.AUTH_USER_MODEL


def _pseudonymise(user_id):
    """One-way hash of user_id for analytics — cannot be reversed."""
    secret = settings.SECRET_KEY[:16].encode()
    return hashlib.sha256(secret + str(user_id).encode()).hexdigest()[:16]


class FunnelEvent(models.Model):
    EVENT = (("view","View"),("add_cart","Add Cart"),("checkout","Checkout"),("purchase","Purchase"))

    # FIX: Store pseudonymous hash, not raw user_id — Lei 22/11 data minimisation
    user_hash = models.CharField(max_length=16, blank=True, db_index=True,
                                  help_text="Pseudonymous hash of user_id — not reversible")
    session_id = models.CharField(max_length=100, blank=True)
    event = models.CharField(max_length=20, choices=EVENT)
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, null=True, blank=True)
    category = models.ForeignKey("products.Category", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "-created_at"]),
            models.Index(fields=["user_hash", "event"]),
        ]

    @classmethod
    def track(cls, user, event, product=None, session_id=""):
        user_hash = _pseudonymise(user.pk) if user and user.is_authenticated else ""
        return cls.objects.create(
            user_hash=user_hash, session_id=session_id,
            event=event, product=product,
            category=product.category if product else None,
        )


class SellerPerformance(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name="performance")
    response_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    avg_response_time_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    completion_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    return_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    overall_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    tier = models.CharField(max_length=10, default="bronze")
    last_calculated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["tier", "-overall_score"])]

    def recalculate(self):
        self.overall_score = (
            self.response_rate * Decimal("0.2") +
            self.on_time_delivery_rate * Decimal("0.4") +
            self.completion_rate * Decimal("0.3") +
            (1 - self.return_rate) * Decimal("0.1")
        ).quantize(Decimal("0.0001"))
        if self.overall_score >= Decimal("0.9"):
            self.tier = "gold"
        elif self.overall_score >= Decimal("0.7"):
            self.tier = "silver"
        else:
            self.tier = "bronze"
        self.save(update_fields=["overall_score", "tier", "last_calculated"])


class GeoSalesData(models.Model):
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100, blank=True)
    order_count = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    period = models.DateField()

    class Meta:
        unique_together = ("city", "period")
        indexes = [models.Index(fields=["period", "-total_revenue"])]
