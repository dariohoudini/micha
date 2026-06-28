"""
MICHA Stock Engine — authoritative multi-state SKU inventory ledger.

Source: MICHA_Inventory_Concurrency.docx (24 chapters).

The headline improvement over the legacy single `Product.quantity` counter:
an explicit per-SKU state ledger (available/reserved/committed/in_transit/
damaged/returned) with the doc's non-oversell invariant enforced as a DB
CHECK constraint — so even a buggy code path cannot oversell (CH1/CH5/CH21).

Chapters that live HERE:
  CH1/2  InventorySku (5-state counters + DB invariant), StockMovement
  CH3    SkuReservation (cart/checkout/flash, TTL, status)
  CH6    FlashStockPool / FlashClaim
  CH11   BackorderDemand
  CH15   RestockSubscription (notify-me)
  CH18/21 StockIntegrityException
  CH24   StockEngineKpiSnapshot

Bridged (not duplicated):
  apps.forecasting               DemandForecast / safety-stock (CH16)
  apps.pricing_inventory.Warehouse / ReturnInventoryReceipt (CH7/CH12)
  apps.inventory.ProductVariantCombo (CH14 variant matrix)
  apps.products.Product          listing status (CH9/CH15)
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from .state_machine import STATES  # noqa: F401

User = settings.AUTH_USER_MODEL


class InventorySku(models.Model):
    """One authoritative stock record per (product, variant, warehouse).

    Invariant (doc CH1): available + reserved + committed + damaged +
    in_transit + returned <= total_quantity, every counter >= 0 — both
    enforced as DB CHECK constraints (the final oversell backstop).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    product_id = models.CharField(max_length=64, db_index=True)
    variant_combo_id = models.CharField(max_length=64, blank=True,
                                        db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='inventory_skus')
    warehouse_id = models.CharField(max_length=64, blank=True, db_index=True)
    sku_code = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=50, blank=True)

    # State counters (doc CH2)
    total_quantity = models.IntegerField(default=0)
    available_quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    committed_quantity = models.IntegerField(default=0)
    in_transit_quantity = models.IntegerField(default=0)
    damaged_quantity = models.IntegerField(default=0)
    returned_quantity = models.IntegerField(default=0)

    # Reorder controls (doc CH1/CH9/CH16)
    safety_stock_qty = models.IntegerField(default=0)
    reorder_qty = models.IntegerField(default=0)
    reorder_point = models.IntegerField(default=0)
    reorder_enabled = models.BooleanField(default=True)

    # Flash sale (doc CH6)
    flash_sale_qty = models.IntegerField(default=0)

    # Backorder / pre-order (doc CH11)
    backorder_enabled = models.BooleanField(default=False)
    backorder_limit = models.IntegerField(default=0)
    expected_restock_date = models.DateField(null=True, blank=True)
    preorder_enabled = models.BooleanField(default=False)
    preorder_ship_date = models.DateField(null=True, blank=True)

    # Physical audit freeze (doc CH10)
    count_locked = models.BooleanField(default=False)

    # Listing visibility (doc CH9/CH15)
    listing_status = models.CharField(
        max_length=16,
        choices=[('active', 'Active'), ('out_of_stock', 'Out of stock'),
                 ('discontinued', 'Discontinued')],
        default='active', db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['seller', 'listing_status']),
            models.Index(fields=['product_id', 'variant_combo_id']),
            models.Index(fields=['available_quantity']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(available_quantity__gte=0) & Q(reserved_quantity__gte=0)
                    & Q(committed_quantity__gte=0) & Q(damaged_quantity__gte=0)
                    & Q(in_transit_quantity__gte=0)
                    & Q(returned_quantity__gte=0)
                    & Q(total_quantity__gte=0)),
                name='stock_qty_non_negative'),
            # The non-oversell invariant (doc CH1) — the final backstop:
            # even a buggy code path that tried to oversell would have its
            # UPDATE rejected here and the transaction rolled back.
            models.CheckConstraint(
                condition=Q(total_quantity__gte=(
                    F('available_quantity') + F('reserved_quantity')
                    + F('committed_quantity') + F('damaged_quantity')
                    + F('in_transit_quantity') + F('returned_quantity'))),
                name='stock_non_oversell_invariant'),
        ]

    def state_sum(self):
        return (self.available_quantity + self.reserved_quantity
                + self.committed_quantity + self.damaged_quantity
                + self.in_transit_quantity + self.returned_quantity)

    def __str__(self):
        return f'sku:{self.sku_code or self.id} avail={self.available_quantity}'


class SkuReservation(models.Model):
    """A hold on stock (doc CH3). cart/checkout/flash with a TTL."""
    TYPE_CHOICES = [('cart', 'Cart (soft)'), ('checkout', 'Checkout (hard)'),
                    ('flash_sale', 'Flash sale')]
    STATUS_CHOICES = [('active', 'Active'), ('committed', 'Committed'),
                      ('released', 'Released'), ('expired', 'Expired')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    sku = models.ForeignKey(InventorySku, on_delete=models.CASCADE,
                            related_name='reservations')
    quantity = models.IntegerField()
    order_id = models.CharField(max_length=64, blank=True, db_index=True)
    cart_id = models.CharField(max_length=64, blank=True, db_index=True)
    reservation_type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='active', db_index=True)
    idempotency_key = models.CharField(max_length=128, blank=True,
                                       db_index=True)
    extensions = models.PositiveSmallIntegerField(default=0)  # max 3 (CH4)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'expires_at'])]


class StockMovement(models.Model):
    """Immutable inventory event log (doc CH18). INSERT only. The running
    sum of quantity_delta reconciles to total_quantity (integrity sweep).
    """
    EVENT_CHOICES = [
        ('reserved', 'Reserved'), ('reservation_released', 'Released'),
        ('committed', 'Committed'), ('shipped', 'Shipped'),
        ('delivered', 'Delivered'), ('returned', 'Returned'),
        ('returned_restocked', 'Returned restocked'),
        ('returned_damaged', 'Returned damaged'), ('damaged', 'Damaged'),
        ('written_off', 'Written off'),
        ('adjusted_positive', 'Adjusted +'), ('adjusted_negative', 'Adjusted -'),
        ('received_inbound', 'Received inbound'),
        ('flash_claimed', 'Flash claimed'),
        ('flash_released', 'Flash released'),
    ]
    id = models.BigAutoField(primary_key=True)
    sku = models.ForeignKey(InventorySku, on_delete=models.CASCADE,
                            related_name='movements')
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES,
                                  db_index=True)
    quantity_delta = models.IntegerField()  # +increase / -decrease to total
    before_available = models.IntegerField(default=0)
    after_available = models.IntegerField(default=0)
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    actor = models.CharField(max_length=100, default='system')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['sku', 'created_at'])]
        ordering = ['created_at']


# ──────────────────────────────────────────────────────────────────────
# CH6 — Flash sale pool
# ──────────────────────────────────────────────────────────────────────

class FlashStockPool(models.Model):
    flash_event_id = models.CharField(max_length=64, db_index=True)
    sku = models.ForeignKey(InventorySku, on_delete=models.CASCADE,
                            related_name='flash_pools')
    allocated_qty = models.IntegerField()
    claimed_qty = models.IntegerField(default=0)
    per_buyer_limit = models.PositiveSmallIntegerField(default=1)
    is_open = models.BooleanField(default=False, db_index=True)
    opens_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    reconciled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('flash_event_id', 'sku')]

    @property
    def remaining(self):
        return max(0, self.allocated_qty - self.claimed_qty)


class FlashClaim(models.Model):
    pool = models.ForeignKey(FlashStockPool, on_delete=models.CASCADE,
                             related_name='claims')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='flash_claims')
    quantity = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('pool', 'buyer')]  # per-buyer limit backstop


# ──────────────────────────────────────────────────────────────────────
# CH11 — Backorder demand (FIFO)
# ──────────────────────────────────────────────────────────────────────

class BackorderDemand(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('allocated', 'Allocated (ready to ship)'),
        ('cancelled', 'Cancelled'),
    ]
    sku = models.ForeignKey(InventorySku, on_delete=models.CASCADE,
                            related_name='backorders')
    order_id = models.CharField(max_length=64, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='backorders')
    quantity = models.IntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    allocated_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH15 — Notify-me restock subscription
# ──────────────────────────────────────────────────────────────────────

class RestockSubscription(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('notified', 'Notified'),
                      ('cancelled', 'Cancelled')]
    sku = models.ForeignKey(InventorySku, on_delete=models.CASCADE,
                            related_name='restock_subs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='restock_subs')
    email = models.EmailField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('sku', 'user')]


# ──────────────────────────────────────────────────────────────────────
# CH18/21 — Integrity exceptions
# ──────────────────────────────────────────────────────────────────────

class StockIntegrityException(models.Model):
    KIND_CHOICES = [
        ('oversell', 'Oversell (available < 0)'),
        ('invariant_breach', 'State sum > total'),
        ('event_sum_mismatch', 'Event running sum != total'),
        ('redis_divergence', 'Redis vs DB divergence'),
    ]
    sku = models.ForeignKey(InventorySku, on_delete=models.CASCADE,
                            related_name='integrity_exceptions')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

class StockEngineKpiSnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    total_active_skus = models.IntegerField(default=0)
    in_stock_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                       default=0)   # >95
    oos_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    active_reservations = models.IntegerField(default=0)
    reservation_conversion_pct = models.DecimalField(max_digits=5,
                                                     decimal_places=2,
                                                     default=0)  # >70
    reservation_expiry_pct = models.DecimalField(max_digits=5,
                                                 decimal_places=2, default=0)
    oversell_incidents = models.IntegerField(default=0)        # 0 tolerance
    integrity_exceptions = models.IntegerField(default=0)
    flash_pools_active = models.IntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)


class StockEngineEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='stock_engine_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            StockEngineEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload)
        except Exception:
            pass
