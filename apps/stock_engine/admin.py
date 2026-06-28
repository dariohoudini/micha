from django.contrib import admin

from .models import (
    BackorderDemand, FlashClaim, FlashStockPool, InventorySku,
    RestockSubscription, SkuReservation, StockEngineEvent,
    StockEngineKpiSnapshot, StockIntegrityException, StockMovement,
)


@admin.register(InventorySku)
class InventorySkuAdmin(admin.ModelAdmin):
    list_display = ('sku_code', 'seller', 'available_quantity',
                    'reserved_quantity', 'committed_quantity',
                    'damaged_quantity', 'total_quantity', 'listing_status')
    list_filter = ('listing_status', 'backorder_enabled', 'count_locked')
    search_fields = ('sku_code', 'product_id', 'barcode')


@admin.register(SkuReservation)
class SkuReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'sku', 'quantity', 'reservation_type', 'status',
                    'order_id', 'expires_at')
    list_filter = ('reservation_type', 'status')
    search_fields = ('order_id', 'cart_id', 'idempotency_key')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('sku', 'event_type', 'quantity_delta', 'before_available',
                    'after_available', 'actor', 'created_at')
    list_filter = ('event_type',)
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FlashStockPool)
class FlashStockPoolAdmin(admin.ModelAdmin):
    list_display = ('flash_event_id', 'sku', 'allocated_qty', 'claimed_qty',
                    'is_open', 'reconciled', 'ends_at')
    list_filter = ('is_open', 'reconciled')


@admin.register(FlashClaim)
class FlashClaimAdmin(admin.ModelAdmin):
    list_display = ('pool', 'buyer', 'quantity', 'created_at')


@admin.register(BackorderDemand)
class BackorderDemandAdmin(admin.ModelAdmin):
    list_display = ('sku', 'order_id', 'quantity', 'status', 'created_at',
                    'allocated_at')
    list_filter = ('status',)


@admin.register(RestockSubscription)
class RestockSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('sku', 'user', 'email', 'status', 'notified_at')
    list_filter = ('status',)


@admin.register(StockIntegrityException)
class StockIntegrityExceptionAdmin(admin.ModelAdmin):
    list_display = ('sku', 'kind', 'resolved', 'detected_at')
    list_filter = ('kind', 'resolved')


@admin.register(StockEngineKpiSnapshot)
class StockEngineKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'total_active_skus', 'in_stock_pct',
                    'oos_pct', 'oversell_incidents', 'integrity_exceptions')


@admin.register(StockEngineEvent)
class StockEngineEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
