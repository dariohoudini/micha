from django.contrib import admin

from .models import (
    Courier, CourierApplication, DeliveryRoute, GpsDeliveryAddress,
    LastMileEvent, LastMileKpiSnapshot, LastMileShipment,
    PackageConsolidation, ProofOfDelivery, ProvinceZone, RouteStop,
    ShipmentEvent, WeightDiscrepancy,
)


@admin.register(ProvinceZone)
class ProvinceZoneAdmin(admin.ModelAdmin):
    list_display = ('origin_province', 'destination_province', 'zone_class',
                    'base_rate_cents', 'rate_per_kg_cents', 'cod_available',
                    'is_active')
    list_filter = ('zone_class', 'cod_available', 'origin_province')


@admin.register(GpsDeliveryAddress)
class GpsDeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'label', 'province', 'bairro', 'quality_score',
                    'verified_by_delivery', 'is_default')
    list_filter = ('province', 'verified_by_delivery',
                   'needs_pin_reverification')
    search_fields = ('landmark', 'bairro')


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'province', 'vehicle_type', 'status',
                    'today_assigned_count', 'current_cod_float_cents',
                    'performance_score', 'security_bonded')
    list_filter = ('province', 'vehicle_type', 'status', 'security_bonded')
    search_fields = ('full_name', 'phone')


@admin.register(CourierApplication)
class CourierApplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'province', 'vehicle_type', 'status',
                    'test_deliveries_done', 'created_at')
    list_filter = ('status', 'province', 'vehicle_type')


@admin.register(LastMileShipment)
class LastMileShipmentAdmin(admin.ModelAdmin):
    list_display = ('micha_tracking_id', 'order_id', 'destination_province',
                    'courier', 'status', 'cod_amount_cents', 'failure_count',
                    'estimated_delivery_date')
    list_filter = ('status', 'destination_province', 'time_window',
                   'failure_type')
    search_fields = ('micha_tracking_id', 'order_id')


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ('shipment', 'status', 'source', 'location_description',
                    'event_time')
    list_filter = ('status', 'source')


@admin.register(DeliveryRoute)
class DeliveryRouteAdmin(admin.ModelAdmin):
    list_display = ('courier', 'route_date', 'total_stops',
                    'total_distance_km', 'optimised_at')


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ('route', 'sequence', 'shipment', 'leg_distance_km')


@admin.register(ProofOfDelivery)
class ProofOfDeliveryAdmin(admin.ModelAdmin):
    list_display = ('shipment', 'otp_verified', 'cod_collected_cents',
                    'proximity_ok', 'captured_offline', 'delivered_at')
    list_filter = ('otp_verified', 'proximity_ok', 'captured_offline')


@admin.register(PackageConsolidation)
class PackageConsolidationAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'seller', 'combined_weight_grams',
                    'combined_rate_cents', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(WeightDiscrepancy)
class WeightDiscrepancyAdmin(admin.ModelAdmin):
    list_display = ('shipment', 'seller', 'declared_grams', 'actual_grams',
                    'delta_pct', 'severity', 'shortfall_cents', 'disputed')
    list_filter = ('severity', 'disputed')


@admin.register(LastMileKpiSnapshot)
class LastMileKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'first_attempt_rate_pct',
                    'delivery_success_pct', 'on_time_pct',
                    'failed_buyer_caused_pct', 'active_couriers')


@admin.register(LastMileEvent)
class LastMileEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
