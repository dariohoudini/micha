from django.contrib import admin

from .models import (
    AddressValidationResult, Carrier, CarrierService,
    CarrierSlaSnapshot, ChoiceLocalFulfilment, CodRemittance,
    CodTransaction, ComplianceRule, CustomsDeclaration,
    CustomsException, DeliveryEtaSnapshot, DutyEstimate,
    FailedDelivery, FulfilmentException, FulfilmentWave,
    HSCodeAssignment, InboundShipmentItem, InsuranceClaim,
    LogisticsEvent, LogisticsKpiSnapshot, PackJob,
    ParcelInsurancePolicy, PickList, PickupPoint,
    PickupPointDelivery, ReturnShipmentLabel,
    ReverseLogisticsRecord, ShippingLabel, StockTransferOrder,
    TrackingNormalisedEvent, TrackingStatusUnified,
    WarehouseInboundShipment,
)


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tier', 'status',
                    'on_time_rate', 'health_score',
                    'average_transit_days')
    list_filter = ('tier', 'status')


@admin.register(CarrierService)
class CarrierServiceAdmin(admin.ModelAdmin):
    list_display = ('carrier', 'code', 'name', 'service_type',
                    'min_transit_days', 'max_transit_days',
                    'base_rate', 'currency', 'is_active')
    list_filter = ('service_type', 'is_active')


@admin.register(ShippingLabel)
class ShippingLabelAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'order_id', 'carrier',
                    'service', 'declared_value', 'status', 'created_at')
    list_filter = ('status', 'carrier')


@admin.register(CustomsDeclaration)
class CustomsDeclarationAdmin(admin.ModelAdmin):
    list_display = ('label', 'sender_country', 'recipient_country',
                    'incoterm', 'declared_total_value',
                    'duty_estimate_amount', 'tax_estimate_amount')
    list_filter = ('incoterm',)


@admin.register(HSCodeAssignment)
class HSCodeAssignmentAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'hs_code', 'confidence',
                    'manually_reviewed', 'classifier_version')
    list_filter = ('manually_reviewed',)


@admin.register(DutyEstimate)
class DutyEstimateAdmin(admin.ModelAdmin):
    list_display = ('hs_code', 'destination_country',
                    'declared_value', 'duty_amount',
                    'vat_amount', 'landed_cost')
    list_filter = ('destination_country',)


@admin.register(ParcelInsurancePolicy)
class ParcelInsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'insured_amount', 'premium_amount',
                    'coverage', 'status', 'valid_until')
    list_filter = ('coverage', 'status')


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ('policy', 'claimant', 'reason',
                    'claim_amount', 'status', 'filed_at')
    list_filter = ('reason', 'status')


@admin.register(TrackingStatusUnified)
class TrackingStatusUnifiedAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'carrier', 'order_id',
                    'current_status', 'last_event_at',
                    'last_known_location', 'delivered_at')
    list_filter = ('current_status', 'carrier')
    search_fields = ('tracking_number', 'order_id')


@admin.register(TrackingNormalisedEvent)
class TrackingNormalisedEventAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'normalised_status',
                    'raw_status', 'location', 'occurred_at')
    list_filter = ('normalised_status',)


@admin.register(DeliveryEtaSnapshot)
class DeliveryEtaSnapshotAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'order_id', 'eta_at',
                    'confidence', 'is_current', 'computed_at')
    list_filter = ('is_current',)


@admin.register(AddressValidationResult)
class AddressValidationResultAdmin(admin.ModelAdmin):
    list_display = ('country', 'valid', 'deliverability_score',
                    'source', 'validated_at')
    list_filter = ('valid', 'country', 'source')


@admin.register(CodTransaction)
class CodTransactionAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'amount', 'currency',
                    'collection_fee', 'status', 'collected_at',
                    'remitted_at')
    list_filter = ('status',)


@admin.register(CodRemittance)
class CodRemittanceAdmin(admin.ModelAdmin):
    list_display = ('batch_reference', 'carrier', 'seller',
                    'total_amount', 'transaction_count',
                    'status', 'settled_at')
    list_filter = ('status',)


@admin.register(ReturnShipmentLabel)
class ReturnShipmentLabelAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'tracking_number', 'buyer',
                    'funded_by', 'status', 'issued_at')
    list_filter = ('status', 'funded_by')


@admin.register(ReverseLogisticsRecord)
class ReverseLogisticsRecordAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'inspection_decision',
                    'grade', 'disposition', 'received_at')
    list_filter = ('inspection_decision', 'grade', 'disposition')


@admin.register(WarehouseInboundShipment)
class WarehouseInboundShipmentAdmin(admin.ModelAdmin):
    list_display = ('asn_reference', 'seller', 'warehouse_code',
                    'expected_arrival_date', 'actual_arrival_at',
                    'status')
    list_filter = ('status',)


@admin.register(InboundShipmentItem)
class InboundShipmentItemAdmin(admin.ModelAdmin):
    list_display = ('shipment', 'product_id', 'sku_id',
                    'expected_qty', 'received_qty', 'rejected_qty')


@admin.register(FulfilmentWave)
class FulfilmentWaveAdmin(admin.ModelAdmin):
    list_display = ('wave_number', 'warehouse_code', 'sla_class',
                    'status', 'planned_for', 'dispatched_at')
    list_filter = ('status', 'sla_class')


@admin.register(PickList)
class PickListAdmin(admin.ModelAdmin):
    list_display = ('wave', 'picker', 'completed',
                    'started_at', 'completed_at')


@admin.register(PackJob)
class PackJobAdmin(admin.ModelAdmin):
    list_display = ('wave', 'order_id', 'parcel_count',
                    'completed', 'completed_at')


@admin.register(StockTransferOrder)
class StockTransferOrderAdmin(admin.ModelAdmin):
    list_display = ('from_warehouse', 'to_warehouse', 'product_id',
                    'quantity', 'status', 'approved_by', 'approved_at')
    list_filter = ('status',)


@admin.register(CarrierSlaSnapshot)
class CarrierSlaSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'carrier', 'service',
                    'destination_country', 'shipments_count',
                    'on_time_pct', 'avg_transit_days')


@admin.register(FailedDelivery)
class FailedDeliveryAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'reason', 'attempt_number',
                    'resolution', 'occurred_at')
    list_filter = ('reason', 'resolution')


@admin.register(CustomsException)
class CustomsExceptionAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'kind', 'resolved',
                    'requires_buyer_action', 'detected_at')
    list_filter = ('kind', 'resolved')


@admin.register(FulfilmentException)
class FulfilmentExceptionAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'kind', 'severity',
                    'resolution', 'resolved', 'detected_at')
    list_filter = ('kind', 'resolved')


@admin.register(PickupPoint)
class PickupPointAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'carrier', 'kind',
                    'country', 'capacity', 'current_load', 'is_active')
    list_filter = ('kind', 'country', 'is_active')


@admin.register(PickupPointDelivery)
class PickupPointDeliveryAdmin(admin.ModelAdmin):
    list_display = ('pickup_point', 'order_id', 'tracking_number',
                    'pickup_code', 'status', 'deadline_at')
    list_filter = ('status',)


@admin.register(ChoiceLocalFulfilment)
class ChoiceLocalFulfilmentAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'warehouse_code',
                    'domestic_carrier', 'sla_met', 'delivered_at')


@admin.register(ComplianceRule)
class ComplianceRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'sender_country', 'recipient_country',
                    'rule_kind', 'enforcement', 'is_active')
    list_filter = ('rule_kind', 'enforcement', 'is_active')


@admin.register(LogisticsKpiSnapshot)
class LogisticsKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'shipments_created',
                    'shipments_delivered', 'on_time_pct',
                    'failed_delivery_count', 'cod_pending_count')


@admin.register(LogisticsEvent)
class LogisticsEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'tracking_number', 'order_id',
                    'seller', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at',
                       'tracking_number', 'order_id',
                       'seller', 'actor')
