"""
Pricing & Inventory Intelligence — data model
=============================================

Implements AliExpress_Pricing_Inventory_Intelligence.docx CH1-CH24
where existing apps don't already own the schema. We intentionally
do NOT duplicate:

  - apps.inventory.ProductVariant / StockReservation / InventoryLog
  - apps.products.PriceTier
  - apps.forecasting.DailyDemand / DemandForecast / ReorderRecommendation
  - apps.fx.FXRate / ConversionEvent
  - apps.shipping.ShippingTemplate
  - apps.marketing_engine.BundleDeal / FlashSaleItem (virtual bundles
    reuse these)

What's new here:

  CH1  PriceRule              — layered rules: base / seller / promo /
                                personalised / experimental
  CH2  DynamicPricingConfig   — per-SKU dynamic-pricing on/off + bounds
       DynamicPriceSignal     — emitted by the workers (time/demand/competitor)
  CH3  PriceFloor             — per-category min markup vs cost (multi-level)
  CH4  PriceCap               — emergency + statistical cap (anti-gouging)
  CH5  PriceHistory           — append-only audit of every price change
  CH6  CompetitorObservation  — internal + external observations
  CH7  RegionalPriceAdjustment — PPP / market overrides
  CH12 PreOrderConfig         — per-SKU pre-order enable + deposit
       PreOrderReservation    — buyer reservation against future stock
  CH13 BackorderConfig        — per-SKU backorder enable + max wait
       BackorderRequest       — outstanding backorders queued by FIFO
  CH14 DropshipSupplier, DropshipMapping — external supplier
       DropshipOrder          — order routed to supplier instead of warehouse
  CH15 Warehouse, WarehouseStock — multi-warehouse + per-SKU inventory
  CH16 InventorySyncJob       — WMS/ERP sync log (push or pull)
       InventoryWebhook       — third-party push events
  CH17 StockAlert             — tiered (critical/low/healthy) with auto-actions
  CH18 ReturnInventoryReceipt — return-side stock reconciliation
  CH19 InventoryAuditRun + InventoryAuditEntry — discrepancy report
  CH20 HazmatClass, ProductHazmat — restricted shipping enforcement
  CH21 OversizeSurchargeRule  — dimensional weight + surcharge
  CH22 VirtualBundleInventory — derived stock from worst-case component
  CH24 PricingInventoryKpiSnapshot

  Audit PricingInventoryEvent — append-only per-product/seller log
"""
from __future__ import annotations

import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────
# CH1 — Layered price rules
# ─────────────────────────────────────────────────────────────────

PRICE_LAYER_CHOICES = (
    ('base',           'Base price (seller list price)'),
    ('seller_override','Seller-set temporary override'),
    ('promotional',    'Promotional layer (flash/coupon/bundle)'),
    ('personalised',   'Personalised offer (segment-specific)'),
    ('experimental',   'A/B experiment override'),
    ('regional',       'Regional / PPP override'),
)

PRICE_RULE_STATUS_CHOICES = (
    ('draft',     'Draft'),
    ('active',    'Active'),
    ('paused',    'Paused'),
    ('superseded','Superseded by higher-priority rule'),
    ('ended',     'Ended'),
)


class PriceRule(models.Model):
    """The unified price rule.  CH1.1 spec — multiple layers can be
    active for the same SKU simultaneously; `services.resolve_price`
    walks them in priority order.

    We keep `product_id` and `sku_id` as plain strings (not FKs) so
    this app can be installed even if `apps.products` isn't loaded
    yet. The resolver tolerates missing references."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    layer = models.CharField(max_length=16, choices=PRICE_LAYER_CHOICES, db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='price_rules',
    )
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    country = models.CharField(max_length=2, blank=True, default='')

    price_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    priority_score = models.PositiveSmallIntegerField(
        default=50,
        help_text='Higher wins ties within the same layer.',
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=PRICE_RULE_STATUS_CHOICES, default='active',
        db_index=True,
    )
    source = models.CharField(
        max_length=40, blank=True, default='',
        help_text='free-text source tag, e.g. "dynamic_engine", "admin_override"',
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_price_rules',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority_score', '-created_at']
        indexes = [
            models.Index(fields=['product_id', 'sku_id', 'status']),
            models.Index(fields=['layer', 'status']),
            models.Index(fields=['valid_from', 'valid_until']),
        ]


# ─────────────────────────────────────────────────────────────────
# CH2 — Dynamic pricing
# ─────────────────────────────────────────────────────────────────

DYNAMIC_SIGNAL_KIND_CHOICES = (
    ('time_decay',      'Time-based decay'),
    ('demand_surge',    'Demand-based surge'),
    ('demand_slump',    'Demand-based slump'),
    ('competitor_under','Undercut competitor'),
    ('competitor_over', 'Match-up to competitor'),
    ('inventory_clear', 'Inventory clearance push'),
)


class DynamicPricingConfig(models.Model):
    """Per-SKU on/off for the dynamic engine, plus bounds so a bad
    signal can't drop the price below cost or above MSRP."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dynamic_pricing_configs')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    enabled = models.BooleanField(default=False)

    # Bounds the dynamic engine must respect.
    min_price = models.DecimalField(max_digits=12, decimal_places=2)
    max_price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_basis = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Signal toggles.
    use_time_signal = models.BooleanField(default=True)
    use_demand_signal = models.BooleanField(default=True)
    use_competitor_signal = models.BooleanField(default=True)

    # Aggressiveness 1-10 — higher = bigger swings.
    aggressiveness = models.PositiveSmallIntegerField(default=5)
    last_applied_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('seller', 'product_id', 'sku_id')]


class DynamicPriceSignal(models.Model):
    """One row per evaluated signal. The combiner picks the
    strongest signal per SKU and writes a PriceRule(layer=experimental
    or seller_override) with the recommended price."""

    id = models.BigAutoField(primary_key=True)
    config = models.ForeignKey(
        DynamicPricingConfig, on_delete=models.CASCADE, related_name='signals',
    )
    kind = models.CharField(max_length=24, choices=DYNAMIC_SIGNAL_KIND_CHOICES)
    suggested_price = models.DecimalField(max_digits=12, decimal_places=2)
    strength = models.FloatField(default=0.0)
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['config', 'occurred_at'])]


# ─────────────────────────────────────────────────────────────────
# CH3 — Price floors per category
# ─────────────────────────────────────────────────────────────────

class PriceFloor(models.Model):
    """Either an absolute floor or a min-markup-vs-cost. The
    enforcement checks BOTH and uses the higher of the two."""

    id = models.BigAutoField(primary_key=True)
    category_id = models.CharField(max_length=64, db_index=True)
    country = models.CharField(max_length=2, blank=True, default='', db_index=True)
    abs_floor = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Absolute minimum allowed price in the floor currency.',
    )
    currency = models.CharField(max_length=3, default='AOA')
    min_markup_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Minimum markup % over cost. e.g. 15.00 = 15%.',
    )
    rationale = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('category_id', 'country')]


# ─────────────────────────────────────────────────────────────────
# CH4 — Price caps (emergency + statistical)
# ─────────────────────────────────────────────────────────────────

CAP_KIND_CHOICES = (
    ('emergency',   'Emergency cap (regulator / event)'),
    ('statistical', 'Statistical outlier cap'),
    ('manual',      'Manual ops cap'),
)


class PriceCap(models.Model):
    """Caps fail-closed: any listing above the cap is auto-suspended.
    `cap_amount` is in `currency`; the cap normaliser handles FX."""

    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=12, choices=CAP_KIND_CHOICES)
    category_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    product_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    country = models.CharField(max_length=2, blank=True, default='', db_index=True)
    cap_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    sigma_threshold = models.FloatField(
        default=3.0,
        help_text='For statistical caps: std-dev multiplier above mean.',
    )
    reason = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH5 — Price history (audit)
# ─────────────────────────────────────────────────────────────────

class PriceHistory(models.Model):
    """Append-only price-change log. Every PriceRule INSERT/UPDATE
    writes a row.  The `was_price` UI shows the highest price in
    the last 30 days from this table — required by EU's Omnibus
    Directive and similar regulations elsewhere."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    country = models.CharField(max_length=2, blank=True, default='')
    previous_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    delta_pct = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    source = models.CharField(max_length=40, blank=True, default='')
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='price_history_entries',
    )
    rule = models.ForeignKey(
        PriceRule, on_delete=models.SET_NULL, null=True, blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['product_id', 'sku_id', '-recorded_at']),
            models.Index(fields=['country', '-recorded_at']),
        ]


# ─────────────────────────────────────────────────────────────────
# CH6 — Competitor monitoring
# ─────────────────────────────────────────────────────────────────

COMPETITOR_SOURCE_CHOICES = (
    ('internal_micha', 'Internal — other MICHA seller'),
    ('amazon',         'Amazon'),
    ('shopify',        'Shopify storefront'),
    ('jumia',          'Jumia'),
    ('kuanza',         'Kuanza'),
    ('manual',         'Manual entry'),
    ('crawler',        'Web crawler'),
)


class CompetitorObservation(models.Model):
    """One scrape / one observation. Aggregations roll up into the
    dynamic pricing competitor_under / competitor_over signals."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    source = models.CharField(max_length=16, choices=COMPETITOR_SOURCE_CHOICES, db_index=True)
    competitor_url = models.URLField(blank=True, default='')
    competitor_seller = models.CharField(max_length=120, blank=True, default='')
    observed_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    in_stock = models.BooleanField(default=True)
    confidence = models.FloatField(default=0.8)
    observed_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH7.2 — Regional / PPP adjustments
# ─────────────────────────────────────────────────────────────────

class RegionalPriceAdjustment(models.Model):
    """Per-(category, country) PPP multiplier OR explicit per-product
    override. Applied during price resolution (layer=regional)."""

    id = models.BigAutoField(primary_key=True)
    country = models.CharField(max_length=2, db_index=True)
    category_id = models.CharField(max_length=64, blank=True, default='')
    product_id = models.CharField(max_length=64, blank=True, default='')
    multiplier = models.DecimalField(
        max_digits=6, decimal_places=4,
        help_text='1.0000 = no change; 0.7000 = 30% discount for that region.',
    )
    rationale = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH12 — Pre-order
# ─────────────────────────────────────────────────────────────────

class PreOrderConfig(models.Model):
    """Seller enables pre-order for a SKU before stock lands. Buyer
    pays a deposit (or full price); we hold until restock."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='preorder_configs')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    enabled = models.BooleanField(default=True)
    deposit_pct = models.PositiveSmallIntegerField(
        default=0,
        help_text='0 = full payment now; 50 = 50% deposit + balance on ship.',
    )
    max_units = models.PositiveIntegerField(default=0)
    reserved_units = models.PositiveIntegerField(default=0)
    expected_ship_at = models.DateTimeField()
    config_text = models.TextField(blank=True, default='')
    cancellation_grace_hours = models.PositiveSmallIntegerField(default=48)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('product_id', 'sku_id')]


class PreOrderReservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(PreOrderConfig, on_delete=models.CASCADE, related_name='reservations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='preorder_reservations')
    quantity = models.PositiveSmallIntegerField(default=1)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    full_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    status = models.CharField(
        max_length=16, default='reserved',
        choices=(('reserved', 'Reserved'), ('cancelled', 'Cancelled'),
                 ('fulfilled', 'Fulfilled'), ('refunded', 'Refunded')),
    )
    psp_intent_id = models.CharField(max_length=120, blank=True, default='')
    reserved_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH13 — Backorder
# ─────────────────────────────────────────────────────────────────

class BackorderConfig(models.Model):
    """Buyer places order when OOS; we promise to fulfil when restock
    arrives, within `max_wait_days`. If we miss the SLA: auto-refund."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='backorder_configs')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    enabled = models.BooleanField(default=False)
    max_wait_days = models.PositiveSmallIntegerField(default=14)
    max_queue = models.PositiveIntegerField(default=0)
    queue_count = models.PositiveIntegerField(default=0)
    expected_restock_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('product_id', 'sku_id')]


class BackorderRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(BackorderConfig, on_delete=models.CASCADE, related_name='requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='backorder_requests')
    quantity = models.PositiveSmallIntegerField(default=1)
    queue_position = models.PositiveIntegerField()
    order_id = models.CharField(max_length=64, blank=True, default='')
    deadline_at = models.DateTimeField()
    status = models.CharField(
        max_length=16, default='queued',
        choices=(('queued', 'Queued'), ('fulfilled', 'Fulfilled'),
                 ('expired', 'Expired SLA'), ('cancelled', 'Cancelled'),
                 ('refunded', 'Refunded')),
    )
    queued_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH14 — Dropshipping
# ─────────────────────────────────────────────────────────────────

class DropshipSupplier(models.Model):
    """External fulfilment partner. The seller maps their SKUs to a
    supplier's SKU; orders for those products are routed direct to
    the supplier instead of using seller-managed inventory."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dropship_suppliers')
    name = models.CharField(max_length=160)
    api_endpoint = models.URLField(blank=True, default='')
    api_key_hash = models.CharField(max_length=64, blank=True, default='')
    region = models.CharField(max_length=2, blank=True, default='')
    average_lead_days = models.PositiveSmallIntegerField(default=14)
    on_time_rate = models.FloatField(default=1.0)
    cancellation_rate = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DropshipMapping(models.Model):
    """SKU bridge: ours → supplier's. Includes cost-of-goods for
    margin computation."""

    id = models.BigAutoField(primary_key=True)
    supplier = models.ForeignKey(DropshipSupplier, on_delete=models.CASCADE, related_name='mappings')
    seller_product_id = models.CharField(max_length=64, db_index=True)
    seller_sku_id = models.CharField(max_length=64, blank=True, default='')
    supplier_sku = models.CharField(max_length=120)
    cost_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('supplier', 'seller_product_id', 'seller_sku_id')]


class DropshipOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(DropshipSupplier, on_delete=models.PROTECT, related_name='orders')
    order_id = models.CharField(max_length=64, db_index=True)
    seller_product_id = models.CharField(max_length=64)
    seller_sku_id = models.CharField(max_length=64, blank=True, default='')
    quantity = models.PositiveSmallIntegerField(default=1)
    supplier_reference = models.CharField(max_length=120, blank=True, default='')
    tracking_number = models.CharField(max_length=80, blank=True, default='')
    sla_deadline_at = models.DateTimeField()
    status = models.CharField(
        max_length=24, default='routed',
        choices=(('routed', 'Routed to supplier'),
                 ('accepted', 'Accepted'),
                 ('shipped', 'Shipped'),
                 ('delivered', 'Delivered'),
                 ('failed', 'Failed by supplier'),
                 ('cancelled', 'Cancelled')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — Multi-warehouse
# ─────────────────────────────────────────────────────────────────

class Warehouse(models.Model):
    """A physical or 3PL fulfilment location."""

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=160)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='warehouses',
    )
    country = models.CharField(max_length=2, db_index=True)
    city = models.CharField(max_length=80, blank=True, default='')
    coords = models.JSONField(
        default=dict, blank=True,
        help_text='{"lat": ..., "lng": ...}',
    )
    capacity_units = models.PositiveIntegerField(default=10000)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WarehouseStock(models.Model):
    """Per-(warehouse, SKU) stock counter. The routing algorithm
    picks the nearest warehouse with enough stock to fulfil."""

    id = models.BigAutoField(primary_key=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stocks')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    on_hand = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    in_transit = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('warehouse', 'product_id', 'sku_id')]

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved)


# ─────────────────────────────────────────────────────────────────
# CH16 — Inventory sync
# ─────────────────────────────────────────────────────────────────

SYNC_DIRECTION_CHOICES = (
    ('push',    'Seller pushes to MICHA (ERP → marketplace)'),
    ('pull',    'MICHA pulls from seller (cron poll)'),
    ('webhook', 'Seller WMS pushes webhooks'),
)


class InventorySyncJob(models.Model):
    """One row per attempted sync. Used by the WMS dashboards to show
    "last sync 3 min ago" and to retry failed pushes."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inventory_sync_jobs')
    direction = models.CharField(max_length=8, choices=SYNC_DIRECTION_CHOICES)
    skus_processed = models.PositiveIntegerField(default=0)
    skus_updated = models.PositiveIntegerField(default=0)
    skus_failed = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, default='running',
        choices=(('running', 'Running'), ('success', 'Success'),
                 ('partial', 'Partial'), ('failed', 'Failed')),
    )
    error_message = models.CharField(max_length=255, blank=True, default='')


class InventoryWebhook(models.Model):
    """Inbound stock-change webhook from a seller's WMS/ERP.
    Idempotent on (seller, external_event_id)."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inventory_webhooks')
    external_event_id = models.CharField(max_length=120)
    product_id = models.CharField(max_length=64)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    new_on_hand = models.IntegerField()
    payload = models.JSONField(default=dict, blank=True)
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'external_event_id')]


# ─────────────────────────────────────────────────────────────────
# CH17 — Stock alert tiers
# ─────────────────────────────────────────────────────────────────

ALERT_TIER_CHOICES = (
    ('healthy',   'Healthy'),
    ('low',       'Low — reorder soon'),
    ('critical',  'Critical — < 3 days of sales'),
    ('out_of_stock', 'OOS'),
)


class StockAlert(models.Model):
    """Per-SKU tiered alert. Auto-action records what we did
    (suppress in search, hide BUY NOW, etc.) so the action can be
    reversed when stock returns."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stock_alerts')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    tier = models.CharField(max_length=12, choices=ALERT_TIER_CHOICES, default='healthy')
    days_of_cover = models.FloatField(default=0)
    on_hand = models.PositiveIntegerField(default=0)
    auto_action = models.CharField(max_length=64, blank=True, default='')
    notified_seller = models.BooleanField(default=False)
    transitioned_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — Return / reverse inventory
# ─────────────────────────────────────────────────────────────────

class ReturnInventoryReceipt(models.Model):
    """When a return arrives back at the warehouse, this row records
    the grading and the decision (restock vs refurbish vs scrap)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='return_receipts')
    order_id = models.CharField(max_length=64, db_index=True)
    return_reason = models.CharField(max_length=120, blank=True, default='')
    product_id = models.CharField(max_length=64)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    quantity = models.PositiveSmallIntegerField(default=1)
    grade = models.CharField(
        max_length=12, default='A',
        choices=(('A', 'A — new, restockable'),
                 ('B', 'B — open box, restock at discount'),
                 ('C', 'C — refurbish'),
                 ('S', 'S — scrap')),
    )
    disposition = models.CharField(
        max_length=12, default='restock',
        choices=(('restock', 'Restock'),
                 ('refurbish', 'Refurbish'),
                 ('scrap', 'Scrap')),
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_receipts',
    )
    received_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH19 — Audit + discrepancy
# ─────────────────────────────────────────────────────────────────

class InventoryAuditRun(models.Model):
    """A scheduled physical count audit. Each entry compares system
    vs physical and writes a discrepancy if they don't match."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_runs')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='audit_runs')
    scheduled_for = models.DateField()
    status = models.CharField(
        max_length=12, default='scheduled',
        choices=(('scheduled', 'Scheduled'), ('running', 'Running'),
                 ('completed', 'Completed'), ('cancelled', 'Cancelled')),
    )
    skus_audited = models.PositiveIntegerField(default=0)
    discrepancy_count = models.PositiveIntegerField(default=0)
    accuracy_rate = models.FloatField(default=1.0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class InventoryAuditEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    run = models.ForeignKey(InventoryAuditRun, on_delete=models.CASCADE, related_name='entries')
    product_id = models.CharField(max_length=64)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    system_on_hand = models.IntegerField()
    physical_count = models.IntegerField()
    delta = models.IntegerField()
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True, default='')
    recorded_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH20 — Dangerous goods
# ─────────────────────────────────────────────────────────────────

HAZMAT_LEVEL_CHOICES = (
    ('none',         'None'),
    ('limited',      'Limited quantity'),
    ('class_2',      'Class 2 — gases'),
    ('class_3',      'Class 3 — flammable liquids'),
    ('class_4',      'Class 4 — flammable solids'),
    ('class_5',      'Class 5 — oxidisers'),
    ('class_6',      'Class 6 — toxic'),
    ('class_8',      'Class 8 — corrosive'),
    ('class_9',      'Class 9 — misc. (lithium batteries etc.)'),
    ('prohibited',   'Prohibited from shipping'),
)


class HazmatClass(models.Model):
    code = models.CharField(max_length=20, primary_key=True)
    label = models.CharField(max_length=80)
    level = models.CharField(max_length=16, choices=HAZMAT_LEVEL_CHOICES)
    requires_un_number = models.BooleanField(default=False)
    requires_safety_data_sheet = models.BooleanField(default=False)
    allowed_carriers = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True, default='')


class ProductHazmat(models.Model):
    """Hazmat declaration per SKU. Set by seller at listing; reviewed
    by ops for high-risk classes."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    hazmat_class = models.ForeignKey(HazmatClass, on_delete=models.PROTECT, related_name='products')
    un_number = models.CharField(max_length=20, blank=True, default='')
    safety_data_sheet_key = models.CharField(max_length=255, blank=True, default='')
    declared_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hazmat_declarations',
    )
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_hazmat',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('product_id', 'sku_id')]


# ─────────────────────────────────────────────────────────────────
# CH21 — Oversize surcharge
# ─────────────────────────────────────────────────────────────────

class OversizeSurchargeRule(models.Model):
    """Dimensional-weight + surcharge rule per (country, carrier).
    Looked up at quote time to add the right shipping surcharge."""

    id = models.BigAutoField(primary_key=True)
    country = models.CharField(max_length=2, blank=True, default='', db_index=True)
    carrier = models.CharField(max_length=32, blank=True, default='')
    dim_factor = models.PositiveIntegerField(
        default=5000,
        help_text='Volumetric weight divisor (cm³/kg).',
    )
    weight_threshold_kg = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('20.00'))
    length_threshold_cm = models.PositiveSmallIntegerField(default=100)
    surcharge_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Virtual bundles
# ─────────────────────────────────────────────────────────────────

class VirtualBundleInventory(models.Model):
    """A virtual bundle's stock is the floor of (component stock /
    component qty needed). Recomputed by the worker on every
    component stock change."""

    id = models.BigAutoField(primary_key=True)
    bundle_id = models.CharField(max_length=64, db_index=True)
    components = models.JSONField(
        default=list,
        help_text='[{product_id, sku_id, quantity_per_bundle}]',
    )
    available_bundles = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ─────────────────────────────────────────────────────────────────

class PricingInventoryKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    # Pricing KPIs
    avg_margin_pct = models.FloatField(default=0)
    price_change_count = models.PositiveIntegerField(default=0)
    price_floor_violations = models.PositiveIntegerField(default=0)
    price_cap_violations = models.PositiveIntegerField(default=0)
    competitor_undercut_pct = models.FloatField(default=0)
    # Inventory KPIs
    avg_stock_accuracy = models.FloatField(default=1.0)
    stockout_skus = models.PositiveIntegerField(default=0)
    critical_skus = models.PositiveIntegerField(default=0)
    preorder_units = models.PositiveIntegerField(default=0)
    backorder_units = models.PositiveIntegerField(default=0)
    dropship_orders = models.PositiveIntegerField(default=0)
    inventory_turn_rate = models.FloatField(default=0)
    return_rate = models.FloatField(default=0)
    by_warehouse = models.JSONField(default=dict, blank=True)
    by_category = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class PricingInventoryEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pricing_inventory_events',
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='emitted_pricing_events',
    )
    kind = models.CharField(max_length=64, db_index=True)
    product_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, seller=None, actor=None, kind, product_id='', payload=None):
        try:
            return PricingInventoryEvent.objects.create(
                seller=seller, actor=actor, kind=kind,
                product_id=product_id, payload=payload or {},
            )
        except Exception:
            return None
