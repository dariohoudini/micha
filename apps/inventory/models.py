from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

User = settings.AUTH_USER_MODEL


class ProductVariant(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=100)
    price_modifier = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["product", "is_active"])]

    def __str__(self):
        return f"{self.product.title} — {self.name}: {self.value}"


class StockReservation(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="reservations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stock_reservations")
    quantity = models.PositiveIntegerField()
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, null=True, blank=True, related_name="stock_reservations")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "expires_at"]),
            models.Index(fields=["product", "is_active"]),
        ]

    @classmethod
    def reserve(cls, product, user, quantity, minutes=15):
        with transaction.atomic():
            from apps.products.models import Product
            p = Product.objects.select_for_update().get(pk=product.pk)
            if p.quantity < quantity:
                raise ValueError(f"Insufficient stock: {p.quantity} available, {quantity} requested")
            p.quantity -= quantity
            p.save(update_fields=["quantity"])
            return cls.objects.create(
                product=p, user=user, quantity=quantity,
                expires_at=timezone.now() + timedelta(minutes=minutes),
            )

    def release(self):
        with transaction.atomic():
            if not self.is_active:
                return
            from apps.products.models import Product
            p = Product.objects.select_for_update().get(pk=self.product_id)
            p.quantity += self.quantity
            if p.quantity > 0 and not p.is_active and not p.is_archived:
                p.is_active = True
            p.save(update_fields=["quantity", "is_active"])
            self.is_active = False
            self.save(update_fields=["is_active"])


class LowStockAlert(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="low_stock_alerts")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="low_stock_alerts")
    threshold = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product", "seller")
        indexes = [models.Index(fields=["seller", "is_active"])]


class InventoryLog(models.Model):
    TYPE = (
        ("purchase", "Purchase"), ("restock", "Restock"),
        ("adjustment", "Adjustment"), ("reservation", "Reservation"),
        ("release", "Release"), ("return", "Return"),
    )
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="inventory_logs")
    type = models.CharField(max_length=15, choices=TYPE)
    quantity_change = models.IntegerField()
    quantity_before = models.IntegerField()
    quantity_after = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["product", "-created_at"])]
