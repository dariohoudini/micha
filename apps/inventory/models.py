from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

User = settings.AUTH_USER_MODEL


class ProductVariant(models.Model):
    """Legacy single-axis variant (kept for back-compat). New code should use ProductVariantCombo."""
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


class ProductVariantCombo(models.Model):
    """One buyable SKU = a specific combination of option values.

    Example for a t-shirt: options = {"Color": "Red", "Size": "M"}
    Each combo has its own price, stock, optional image (e.g. swatch), and SKU.
    Frontend derives axes (Color, Size) by inspecting all combos for a product.
    """
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="variant_combos")
    options = models.JSONField(default=dict, help_text='e.g. {"Color": "Red", "Size": "M"}')
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Absolute price for this combo")
    quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to="variant_images/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["product", "is_active"])]
        ordering = ["id"]

    def __str__(self):
        opts = ", ".join(f"{k}: {v}" for k, v in (self.options or {}).items())
        return f"{self.product.title} — {opts}"

    @property
    def label(self):
        return " / ".join(str(v) for v in (self.options or {}).values())


class StockReservation(models.Model):
    """A short-lived inventory hold attached to a buyer.

    Reservation model
    ──────────────────
    A reservation decrements the canonical stock counter (Product.quantity
    for a non-variant product; ProductVariantCombo.quantity for a variant
    SKU) and keeps it decremented until either:

      • released — abandoned cart / explicit release / expiry sweep
      • committed — the order paid + checkout completed; the row is dropped
        but the decrement stays (now permanent sale)

    Why a separate `variant_combo` FK
    ──────────────────────────────────
    The original model only knew about Product. When a buyer reserved
    "Red M" of a t-shirt, only Product.quantity was decremented — the
    ProductVariantCombo("Red M").quantity stayed unchanged. Two
    concurrent buyers could BOTH reserve the last "Red M" because each
    saw combo.quantity unchanged from view-time. Variant oversell.

    Per-buyer cap
    ──────────────
    A single buyer may hold at most ``MAX_ACTIVE_RESERVATIONS_PER_USER``
    active reservations. Without this a script can spam reserve() and
    starve all other buyers of inventory until expiry sweeps run.

    Mutations go through ``apps.inventory.service`` (the chokepoint).
    Direct ``StockReservation.objects.create()`` is a smell — it bypasses
    the atomic decrement, the cap, and the idempotency key.
    """

    # Cap on active reservations per user. Tune from ops data.
    MAX_ACTIVE_RESERVATIONS_PER_USER = 20

    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE,
        related_name="reservations",
        # nullable so a variant-combo reservation doesn't have to also
        # pin the parent product row (avoiding double-decrement bugs).
        null=True, blank=True,
    )
    variant_combo = models.ForeignKey(
        "inventory.ProductVariantCombo", on_delete=models.CASCADE,
        related_name="reservations", null=True, blank=True,
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stock_reservations")
    quantity = models.PositiveIntegerField()
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, null=True, blank=True, related_name="stock_reservations")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Idempotency key bound to (user, key). Allows safe retry of the
    # reserve endpoint: same key + same target = returns the existing
    # reservation row, no double-decrement.
    idempotency_key = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "expires_at"]),
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["variant_combo", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]
        constraints = [
            # A reservation targets EITHER a product OR a variant combo,
            # not both — checkout decrements them independently and
            # mixing them would double-count.
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant_combo__isnull=True)
                    | models.Q(product__isnull=True, variant_combo__isnull=False)
                ),
                name='reservation_one_target',
            ),
            # Idempotency: a (user, key) pair maps to exactly one row
            # while active. Sparse partial index (Postgres) — SQLite
            # treats the empty-string convention below as OK.
            models.UniqueConstraint(
                fields=['user', 'idempotency_key'],
                condition=models.Q(is_active=True) & ~models.Q(idempotency_key=''),
                name='uniq_user_active_idem_key',
            ),
        ]

    # ── Back-compat classmethod ───────────────────────────────────────
    # New code MUST use ``apps.inventory.service.reserve``. This shim is
    # preserved so older callers that imported ``StockReservation.reserve``
    # don't break in the same release. It now delegates to the service.

    @classmethod
    def reserve(cls, product, user, quantity, minutes=15):
        from .service import reserve as svc_reserve
        return svc_reserve(
            user=user, product=product, quantity=quantity, minutes=minutes,
        )

    def release(self):
        from .service import release_reservation
        release_reservation(self)


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
