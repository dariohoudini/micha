from django.contrib import admin

from .models import (
    BackorderConfig, BackorderRequest, CompetitorObservation,
    DropshipMapping, DropshipOrder, DropshipSupplier,
    DynamicPriceSignal, DynamicPricingConfig, HazmatClass,
    InventoryAuditEntry, InventoryAuditRun, InventorySyncJob,
    InventoryWebhook, OversizeSurchargeRule, PreOrderConfig,
    PreOrderReservation, PriceCap, PriceFloor, PriceHistory,
    PriceRule, PricingInventoryEvent, PricingInventoryKpiSnapshot,
    ProductHazmat, RegionalPriceAdjustment, ReturnInventoryReceipt,
    StockAlert, VirtualBundleInventory, Warehouse, WarehouseStock,
)


@admin.register(PriceRule)
class PriceRuleAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'sku_id', 'layer', 'price_amount',
                    'currency', 'status', 'valid_from', 'valid_until')
    list_filter = ('layer', 'status', 'currency')


@admin.register(DynamicPricingConfig)
class DynamicPricingConfigAdmin(admin.ModelAdmin):
    list_display = ('seller', 'product_id', 'sku_id', 'enabled',
                    'min_price', 'max_price', 'aggressiveness',
                    'last_applied_at')
    list_filter = ('enabled',)


@admin.register(DynamicPriceSignal)
class DynamicPriceSignalAdmin(admin.ModelAdmin):
    list_display = ('config', 'kind', 'suggested_price',
                    'strength', 'occurred_at')
    list_filter = ('kind',)


@admin.register(PriceFloor)
class PriceFloorAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'country', 'abs_floor',
                    'min_markup_pct', 'is_active')
    list_filter = ('country', 'is_active')


@admin.register(PriceCap)
class PriceCapAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'product_id', 'country',
                    'kind', 'cap_amount', 'is_active')
    list_filter = ('kind', 'country', 'is_active')


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'sku_id', 'previous_price',
                    'new_price', 'delta_pct', 'source', 'recorded_at')


@admin.register(CompetitorObservation)
class CompetitorObservationAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'source', 'observed_price',
                    'currency', 'in_stock', 'observed_at')
    list_filter = ('source', 'in_stock')


@admin.register(RegionalPriceAdjustment)
class RegionalPriceAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('country', 'category_id', 'product_id',
                    'multiplier', 'is_active', 'valid_until')
    list_filter = ('country', 'is_active')


@admin.register(PreOrderConfig)
class PreOrderConfigAdmin(admin.ModelAdmin):
    list_display = ('seller', 'product_id', 'sku_id', 'enabled',
                    'deposit_pct', 'reserved_units', 'max_units',
                    'expected_ship_at')


@admin.register(PreOrderReservation)
class PreOrderReservationAdmin(admin.ModelAdmin):
    list_display = ('user', 'config', 'quantity', 'status',
                    'deposit_amount', 'reserved_at')
    list_filter = ('status',)


@admin.register(BackorderConfig)
class BackorderConfigAdmin(admin.ModelAdmin):
    list_display = ('seller', 'product_id', 'sku_id', 'enabled',
                    'max_wait_days', 'queue_count', 'expected_restock_at')


@admin.register(BackorderRequest)
class BackorderRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'config', 'quantity', 'queue_position',
                    'status', 'deadline_at')
    list_filter = ('status',)


@admin.register(DropshipSupplier)
class DropshipSupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'region', 'average_lead_days',
                    'on_time_rate', 'is_active')


@admin.register(DropshipMapping)
class DropshipMappingAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'seller_product_id', 'supplier_sku',
                    'cost_amount', 'currency', 'is_active')


@admin.register(DropshipOrder)
class DropshipOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'supplier', 'seller_product_id',
                    'quantity', 'status', 'sla_deadline_at')
    list_filter = ('status',)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'seller', 'country',
                    'capacity_units', 'is_active')
    list_filter = ('country', 'is_active')


@admin.register(WarehouseStock)
class WarehouseStockAdmin(admin.ModelAdmin):
    list_display = ('warehouse', 'product_id', 'sku_id',
                    'on_hand', 'reserved', 'in_transit', 'updated_at')


@admin.register(InventorySyncJob)
class InventorySyncJobAdmin(admin.ModelAdmin):
    list_display = ('seller', 'direction', 'skus_processed',
                    'skus_updated', 'skus_failed', 'status',
                    'started_at', 'finished_at')
    list_filter = ('direction', 'status')


@admin.register(InventoryWebhook)
class InventoryWebhookAdmin(admin.ModelAdmin):
    list_display = ('seller', 'product_id', 'sku_id',
                    'new_on_hand', 'processed', 'received_at')
    list_filter = ('processed',)


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ('seller', 'product_id', 'tier',
                    'days_of_cover', 'on_hand', 'auto_action',
                    'transitioned_at')
    list_filter = ('tier',)


@admin.register(ReturnInventoryReceipt)
class ReturnInventoryReceiptAdmin(admin.ModelAdmin):
    list_display = ('seller', 'order_id', 'product_id',
                    'quantity', 'grade', 'disposition', 'received_at')
    list_filter = ('grade', 'disposition')


@admin.register(InventoryAuditRun)
class InventoryAuditRunAdmin(admin.ModelAdmin):
    list_display = ('seller', 'warehouse', 'scheduled_for',
                    'status', 'skus_audited', 'discrepancy_count',
                    'accuracy_rate')
    list_filter = ('status',)


@admin.register(InventoryAuditEntry)
class InventoryAuditEntryAdmin(admin.ModelAdmin):
    list_display = ('run', 'product_id', 'sku_id',
                    'system_on_hand', 'physical_count', 'delta',
                    'resolved')
    list_filter = ('resolved',)


@admin.register(HazmatClass)
class HazmatClassAdmin(admin.ModelAdmin):
    list_display = ('code', 'label', 'level',
                    'requires_un_number', 'requires_safety_data_sheet')
    list_filter = ('level',)


@admin.register(ProductHazmat)
class ProductHazmatAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'sku_id', 'hazmat_class',
                    'un_number', 'reviewed', 'created_at')
    list_filter = ('reviewed',)


@admin.register(OversizeSurchargeRule)
class OversizeSurchargeRuleAdmin(admin.ModelAdmin):
    list_display = ('country', 'carrier', 'dim_factor',
                    'weight_threshold_kg', 'length_threshold_cm',
                    'surcharge_amount', 'is_active')


@admin.register(VirtualBundleInventory)
class VirtualBundleInventoryAdmin(admin.ModelAdmin):
    list_display = ('bundle_id', 'available_bundles', 'computed_at')


@admin.register(PricingInventoryKpiSnapshot)
class PricingInventoryKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'price_change_count',
                    'stockout_skus', 'critical_skus',
                    'preorder_units', 'backorder_units',
                    'dropship_orders')


@admin.register(PricingInventoryEvent)
class PricingInventoryEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'product_id', 'seller', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at',
                       'product_id', 'seller', 'actor')
