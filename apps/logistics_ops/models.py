"""
Logistics & Fulfilment Operations — data model
==============================================

Implements AliExpress_Logistics_Fulfilment_Operations.docx CH1-CH24.
Existing apps we DO NOT duplicate:

  - apps.shipping.ShippingTemplate / ShippingMethod / ShippingAddress / DeliveryZone
  - apps.orders.Order / OrderItem / OrderTrackingEvent
  - apps.pricing_inventory.Warehouse / WarehouseStock / HazmatClass /
    ProductHazmat / OversizeSurchargeRule

New tables in this app cover the parts NOT yet shipped:

  CH1   Carrier, CarrierService     — tier + capabilities + rate cards
  CH3   ShippingLabel               — generated labels per shipment
  CH4   CustomsDeclaration, HSCodeAssignment
  CH5   DutyEstimate                — landed cost (DDP vs DAP)
  CH6   ParcelInsurancePolicy, InsuranceClaim
  CH7   TrackingStatusUnified, TrackingNormalisedEvent
  CH8   DeliveryEtaSnapshot
  CH9   AddressValidationResult
  CH12  CodTransaction, CodRemittance
  CH13  ReturnShipmentLabel
  CH14  ReverseLogisticsRecord
  CH15  WarehouseInboundShipment, InboundShipmentItem
  CH16  FulfilmentWave, PickList, PackJob
  CH17  StockTransferOrder
  CH18  CarrierSlaSnapshot, FailedDelivery
  CH19  CustomsException
  CH20  FulfilmentException
  CH21  PickupPoint, PickupPointDelivery
  CH22  ChoiceLocalFulfilment
  CH23  ComplianceRule
  CH24  LogisticsKpiSnapshot
  Audit LogisticsEvent
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
# CH1 — Carriers
# ─────────────────────────────────────────────────────────────────

CARRIER_TIER_CHOICES = (
    ('tier1_global',  'Tier 1 — Global integrator (DHL/FedEx/UPS)'),
    ('tier2_regional','Tier 2 — Regional (Aramex, La Poste, Correos)'),
    ('tier3_local',   'Tier 3 — Local / national post'),
    ('tier4_choice',  'Tier 4 — Choice / Cainiao-managed'),
    ('tier5_dropship','Tier 5 — Supplier-managed'),
)

CARRIER_STATUS_CHOICES = (
    ('active',    'Active'),
    ('paused',    'Paused — temporary'),
    ('disabled',  'Disabled'),
)


class Carrier(models.Model):
    """A logistics provider. The adapter implementation lives in
    `carriers/<code>.py`; this DB row carries the config + auth +
    health metrics."""

    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=120)
    tier = models.CharField(max_length=20, choices=CARRIER_TIER_CHOICES)
    country_scope = models.JSONField(
        default=list, blank=True,
        help_text='ISO codes the carrier serves; empty = global.',
    )
    supports_ddp = models.BooleanField(default=False)
    supports_cod = models.BooleanField(default=False)
    supports_dangerous_goods = models.BooleanField(default=False)
    supports_oversize = models.BooleanField(default=True)
    api_endpoint = models.URLField(blank=True, default='')
    api_key_hash = models.CharField(max_length=64, blank=True, default='')
    webhook_secret_hash = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(
        max_length=12, choices=CARRIER_STATUS_CHOICES, default='active',
        db_index=True,
    )
    on_time_rate = models.FloatField(default=1.0)
    average_transit_days = models.PositiveSmallIntegerField(default=7)
    health_score = models.PositiveSmallIntegerField(
        default=100,
        help_text='0–100 rolling health; sub-60 triggers fallback.',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class CarrierService(models.Model):
    """A specific shipping method offered by a carrier — e.g.
    DHL Express, DHL Economy. Has its own SLA, rate card, and
    capabilities."""

    id = models.BigAutoField(primary_key=True)
    carrier = models.ForeignKey(Carrier, on_delete=models.CASCADE, related_name='services')
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    service_type = models.CharField(
        max_length=20,
        choices=(('express', 'Express'), ('standard', 'Standard'),
                 ('economy', 'Economy'), ('parcel_post', 'Parcel post')),
    )
    min_transit_days = models.PositiveSmallIntegerField()
    max_transit_days = models.PositiveSmallIntegerField()
    base_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    per_kg_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    max_weight_kg = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('30'))
    supports_tracking = models.BooleanField(default=True)
    supports_signature = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('carrier', 'code')]


# ─────────────────────────────────────────────────────────────────
# CH3 — Shipping labels
# ─────────────────────────────────────────────────────────────────

LABEL_STATUS_CHOICES = (
    ('requested', 'Requested'),
    ('generated', 'Generated'),
    ('failed',    'Failed'),
    ('voided',    'Voided'),
)


class ShippingLabel(models.Model):
    """One row per generated shipment label. The PDF / PNG payload is
    stored at `file_key` (S3 / local storage)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_labels')
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT)
    service = models.ForeignKey(CarrierService, on_delete=models.PROTECT)
    tracking_number = models.CharField(max_length=80, unique=True, db_index=True)
    file_key = models.CharField(max_length=255, blank=True, default='')
    format = models.CharField(
        max_length=8, default='pdf',
        choices=(('pdf', 'PDF'), ('png', 'PNG'), ('zpl', 'ZPL')),
    )
    from_address = models.JSONField(default=dict)
    to_address = models.JSONField(default=dict)
    parcel_weight_kg = models.DecimalField(max_digits=6, decimal_places=2)
    parcel_dimensions_cm = models.JSONField(
        default=dict, blank=True,
        help_text='{"length":..,"width":..,"height":..}',
    )
    declared_value = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    status = models.CharField(max_length=12, choices=LABEL_STATUS_CHOICES, default='requested')
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def make_tracking_number(prefix: str = 'MK') -> str:
        return f'{prefix}{secrets.token_hex(8).upper()}'


# ─────────────────────────────────────────────────────────────────
# CH4 — Customs declarations
# ─────────────────────────────────────────────────────────────────

class CustomsDeclaration(models.Model):
    """Cross-border declaration for a shipment. Generated alongside
    the label; the commercial invoice PDF is stored at `invoice_key`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.OneToOneField(ShippingLabel, on_delete=models.CASCADE, related_name='customs')
    sender_country = models.CharField(max_length=2)
    recipient_country = models.CharField(max_length=2)
    incoterm = models.CharField(
        max_length=4, default='DAP',
        choices=(('DDP', 'DDP — duties paid'),
                 ('DAP', 'DAP — duties on arrival'),
                 ('FCA', 'FCA'),
                 ('EXW', 'EXW')),
    )
    items = models.JSONField(default=list)
    declared_total_value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    invoice_key = models.CharField(max_length=255, blank=True, default='')
    eori_number = models.CharField(max_length=40, blank=True, default='')
    duty_estimate_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_estimate_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class HSCodeAssignment(models.Model):
    """ML-assigned HS code per product. Confidence < 0.7 → human review."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    hs_code = models.CharField(max_length=12)
    confidence = models.FloatField(default=0.0)
    classifier_version = models.CharField(max_length=20, blank=True, default='')
    manually_reviewed = models.BooleanField(default=False)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hs_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('product_id', 'hs_code')]


# ─────────────────────────────────────────────────────────────────
# CH5 — Duty / landed cost
# ─────────────────────────────────────────────────────────────────

class DutyEstimate(models.Model):
    """Computed duty + VAT for a (HS code × destination country)
    combo. Cached for 24h to avoid re-hitting the tariff API."""

    id = models.BigAutoField(primary_key=True)
    hs_code = models.CharField(max_length=12, db_index=True)
    destination_country = models.CharField(max_length=2, db_index=True)
    declared_value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    duty_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    vat_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    duty_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    landed_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    incoterm = models.CharField(max_length=4, default='DAP')
    source = models.CharField(max_length=20, default='internal_table')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH6 — Parcel insurance
# ─────────────────────────────────────────────────────────────────

INSURANCE_STATUS_CHOICES = (
    ('active',    'Active'),
    ('claimed',   'Claim filed'),
    ('paid_out',  'Paid out'),
    ('rejected',  'Rejected'),
    ('expired',   'Expired'),
)


class ParcelInsurancePolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    label = models.ForeignKey(
        ShippingLabel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='insurance_policies',
    )
    insured_amount = models.DecimalField(max_digits=12, decimal_places=2)
    premium_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    coverage = models.CharField(
        max_length=20, default='loss_damage',
        choices=(('loss_damage', 'Loss + damage'),
                 ('full', 'Full — loss + damage + delay')),
    )
    status = models.CharField(max_length=12, choices=INSURANCE_STATUS_CHOICES, default='active')
    valid_from = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField()


class InsuranceClaim(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(ParcelInsurancePolicy, on_delete=models.CASCADE, related_name='claims')
    claimant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='insurance_claims')
    reason = models.CharField(
        max_length=24,
        choices=(('lost', 'Lost'), ('damaged', 'Damaged'),
                 ('partial_damage', 'Partial damage'),
                 ('delivery_delay', 'Delivery delay'),
                 ('stolen', 'Stolen / theft')),
    )
    description = models.TextField(blank=True, default='')
    evidence_keys = models.JSONField(default=list, blank=True)
    claim_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=16, default='filed',
        choices=(('filed', 'Filed'), ('under_review', 'Under review'),
                 ('approved', 'Approved'), ('rejected', 'Rejected'),
                 ('paid', 'Paid out'), ('appealed', 'Appealed')),
    )
    decision_notes = models.TextField(blank=True, default='')
    decided_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    filed_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH7 — Unified tracking
# ─────────────────────────────────────────────────────────────────

# CH7.1 — the canonical statuses every carrier event normalises into.
TRACKING_STATUS_CHOICES = (
    ('label_created',       'Label created'),
    ('picked_up',           'Picked up by carrier'),
    ('in_transit',          'In transit'),
    ('customs_clearance',   'Customs clearance'),
    ('customs_held',        'Customs hold'),
    ('out_for_delivery',    'Out for delivery'),
    ('delivery_attempted',  'Delivery attempted'),
    ('delivered',           'Delivered'),
    ('exception',           'Exception'),
    ('lost',                'Lost'),
    ('returned_to_sender',  'Returned to sender'),
    ('cancelled',           'Cancelled'),
)


class TrackingStatusUnified(models.Model):
    """Current normalised tracking state per shipment. Updated by the
    normalisation pipeline on every inbound carrier event."""

    tracking_number = models.CharField(max_length=80, primary_key=True)
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT, related_name='tracked_shipments')
    order_id = models.CharField(max_length=64, db_index=True)
    current_status = models.CharField(max_length=24, choices=TRACKING_STATUS_CHOICES, db_index=True)
    last_event_at = models.DateTimeField()
    last_known_location = models.CharField(max_length=120, blank=True, default='')
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)


class TrackingNormalisedEvent(models.Model):
    """Append-only event log. Every webhook / poll writes a row;
    the dedup key is (tracking_number, carrier_event_id)."""

    id = models.BigAutoField(primary_key=True)
    tracking_number = models.CharField(max_length=80, db_index=True)
    carrier_event_id = models.CharField(max_length=120, db_index=True)
    raw_status = models.CharField(max_length=80)
    normalised_status = models.CharField(max_length=24, choices=TRACKING_STATUS_CHOICES)
    classifier_confidence = models.FloatField(default=1.0)
    location = models.CharField(max_length=120, blank=True, default='')
    raw_payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('tracking_number', 'carrier_event_id')]
        indexes = [models.Index(fields=['tracking_number', 'occurred_at'])]


# ─────────────────────────────────────────────────────────────────
# CH8 — ETA snapshots
# ─────────────────────────────────────────────────────────────────

class DeliveryEtaSnapshot(models.Model):
    """A single ETA calculation. Refreshed at checkout, on payment,
    and after each significant tracking event."""

    id = models.BigAutoField(primary_key=True)
    order_id = models.CharField(max_length=64, db_index=True)
    tracking_number = models.CharField(max_length=80, blank=True, default='', db_index=True)
    eta_at = models.DateTimeField()
    confidence = models.FloatField(default=0.7)
    rationale = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True)
    computed_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH9 — Address validation
# ─────────────────────────────────────────────────────────────────

class AddressValidationResult(models.Model):
    """Persisted output of the address validation pipeline. Keyed by
    a content hash so the same input always returns the same row."""

    address_hash = models.CharField(max_length=64, primary_key=True)
    raw_address = models.JSONField(default=dict)
    standardised = models.JSONField(default=dict, blank=True)
    country = models.CharField(max_length=2, db_index=True)
    valid = models.BooleanField(default=False)
    deliverability_score = models.FloatField(default=0.0)
    suggestions = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=20, default='internal')
    validated_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH12 — Cash on delivery
# ─────────────────────────────────────────────────────────────────

COD_STATUS_CHOICES = (
    ('pending',    'Pending — awaiting collection'),
    ('collected',  'Collected by carrier'),
    ('remitted',   'Remitted to merchant'),
    ('failed',     'Failed — customer refused'),
    ('refunded',   'Refunded'),
)


class CodTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    label = models.OneToOneField(ShippingLabel, on_delete=models.CASCADE, related_name='cod')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    collection_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=COD_STATUS_CHOICES, default='pending', db_index=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    remitted_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CodRemittance(models.Model):
    """A batch payout from carrier to merchant for collected COD
    amounts."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT, related_name='cod_remittances')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cod_remittances')
    batch_reference = models.CharField(max_length=80, unique=True, db_index=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    transaction_count = models.PositiveIntegerField(default=0)
    transactions = models.ManyToManyField(CodTransaction, related_name='remittance_batches')
    status = models.CharField(
        max_length=12, default='pending',
        choices=(('pending', 'Pending'), ('confirmed', 'Confirmed'),
                 ('settled', 'Settled'), ('disputed', 'Disputed')),
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH13 — Return shipment labels
# ─────────────────────────────────────────────────────────────────

class ReturnShipmentLabel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='return_labels')
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT)
    service = models.ForeignKey(CarrierService, on_delete=models.PROTECT)
    tracking_number = models.CharField(max_length=80, unique=True, db_index=True)
    file_key = models.CharField(max_length=255, blank=True, default='')
    return_address = models.JSONField(default=dict)
    funded_by = models.CharField(
        max_length=12, default='buyer',
        choices=(('buyer', 'Buyer'), ('seller', 'Seller'),
                 ('platform', 'Platform')),
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    status = models.CharField(
        max_length=16, default='issued',
        choices=(('issued', 'Issued'), ('in_transit', 'In transit'),
                 ('received', 'Received'), ('expired', 'Expired'),
                 ('voided', 'Voided')),
    )
    issued_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH14 — Reverse logistics
# ─────────────────────────────────────────────────────────────────

class ReverseLogisticsRecord(models.Model):
    """A return parcel processed at the warehouse. Linked to the
    original outbound label for traceability."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    return_label = models.ForeignKey(
        ReturnShipmentLabel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reverse_records',
    )
    received_at = models.DateTimeField()
    inspection_decision = models.CharField(
        max_length=20,
        choices=(('accept_full_refund', 'Accept — full refund'),
                 ('accept_partial', 'Accept — partial refund'),
                 ('refuse_return', 'Refuse return'),
                 ('escalate', 'Escalate to ops')),
    )
    inspector_notes = models.TextField(blank=True, default='')
    grade = models.CharField(
        max_length=2, default='A',
        choices=(('A', 'A — new'), ('B', 'B — open box'),
                 ('C', 'C — refurb'), ('S', 'S — scrap')),
    )
    disposition = models.CharField(
        max_length=12, default='restock',
        choices=(('restock', 'Restock'), ('refurbish', 'Refurbish'),
                 ('scrap', 'Scrap'), ('donate', 'Donate'),
                 ('liquidate', 'Liquidate')),
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — Inbound shipments to warehouse
# ─────────────────────────────────────────────────────────────────

INBOUND_STATUS_CHOICES = (
    ('booked',    'Booked — awaiting dispatch by seller'),
    ('in_transit','In transit to warehouse'),
    ('received',  'Received — pending QC'),
    ('qc_passed', 'QC passed — stock on hand'),
    ('partial',   'Partial — some discrepancy'),
    ('rejected',  'Rejected — return to seller'),
)


class WarehouseInboundShipment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inbound_shipments')
    warehouse_code = models.CharField(max_length=20, db_index=True)
    asn_reference = models.CharField(max_length=64, unique=True, db_index=True)
    expected_arrival_date = models.DateField()
    actual_arrival_at = models.DateTimeField(null=True, blank=True)
    carrier = models.ForeignKey(Carrier, on_delete=models.SET_NULL, null=True, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True, default='', db_index=True)
    status = models.CharField(max_length=12, choices=INBOUND_STATUS_CHOICES, default='booked')
    created_at = models.DateTimeField(auto_now_add=True)


class InboundShipmentItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    shipment = models.ForeignKey(WarehouseInboundShipment, on_delete=models.CASCADE, related_name='items')
    product_id = models.CharField(max_length=64)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    expected_qty = models.PositiveIntegerField()
    received_qty = models.PositiveIntegerField(default=0)
    rejected_qty = models.PositiveIntegerField(default=0)
    discrepancy_reason = models.CharField(max_length=120, blank=True, default='')


# ─────────────────────────────────────────────────────────────────
# CH16 — Warehouse outbound (waves / picking / packing)
# ─────────────────────────────────────────────────────────────────

WAVE_STATUS_CHOICES = (
    ('planned',   'Planned'),
    ('released',  'Released to pickers'),
    ('picking',   'Picking in progress'),
    ('packing',   'Packing'),
    ('dispatched','Dispatched'),
    ('cancelled', 'Cancelled'),
)


class FulfilmentWave(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    warehouse_code = models.CharField(max_length=20, db_index=True)
    wave_number = models.CharField(max_length=32, unique=True)
    planned_for = models.DateTimeField()
    order_ids = models.JSONField(default=list)
    sla_class = models.CharField(
        max_length=12, default='standard',
        choices=(('rush', 'Rush'), ('standard', 'Standard'),
                 ('economy', 'Economy')),
    )
    status = models.CharField(max_length=12, choices=WAVE_STATUS_CHOICES, default='planned')
    pick_started_at = models.DateTimeField(null=True, blank=True)
    pack_started_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PickList(models.Model):
    id = models.BigAutoField(primary_key=True)
    wave = models.ForeignKey(FulfilmentWave, on_delete=models.CASCADE, related_name='picklists')
    picker = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='picklists_assigned',
    )
    skus = models.JSONField(default=list)
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class PackJob(models.Model):
    id = models.BigAutoField(primary_key=True)
    wave = models.ForeignKey(FulfilmentWave, on_delete=models.CASCADE, related_name='packjobs')
    order_id = models.CharField(max_length=64, db_index=True)
    parcel_count = models.PositiveSmallIntegerField(default=1)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH17 — Stock transfers
# ─────────────────────────────────────────────────────────────────

TRANSFER_STATUS_CHOICES = (
    ('proposed',  'Proposed by AI'),
    ('approved',  'Approved'),
    ('rejected',  'Rejected'),
    ('in_transit','In transit'),
    ('received',  'Received'),
    ('cancelled', 'Cancelled'),
)


class StockTransferOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_warehouse = models.CharField(max_length=20, db_index=True)
    to_warehouse = models.CharField(max_length=20, db_index=True)
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, default='')
    quantity = models.PositiveIntegerField()
    rationale = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=12, choices=TRANSFER_STATUS_CHOICES, default='proposed')
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_transfers',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — SLA + failed delivery
# ─────────────────────────────────────────────────────────────────

class CarrierSlaSnapshot(models.Model):
    """Daily SLA roll-up per carrier × service × destination. Used by
    the carrier-selection ranking and by the SLA-breach alert task."""

    id = models.BigAutoField(primary_key=True)
    snapshot_date = models.DateField()
    carrier = models.ForeignKey(Carrier, on_delete=models.CASCADE, related_name='sla_snapshots')
    service = models.ForeignKey(CarrierService, on_delete=models.CASCADE, related_name='sla_snapshots')
    destination_country = models.CharField(max_length=2)
    shipments_count = models.PositiveIntegerField(default=0)
    on_time_count = models.PositiveIntegerField(default=0)
    late_count = models.PositiveIntegerField(default=0)
    lost_count = models.PositiveIntegerField(default=0)
    avg_transit_days = models.FloatField(default=0)
    on_time_pct = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('snapshot_date', 'carrier', 'service', 'destination_country')]


FAILED_DELIVERY_REASON_CHOICES = (
    ('recipient_not_home',  'Recipient not home'),
    ('address_incorrect',   'Address incorrect'),
    ('refused_by_recipient','Refused by recipient'),
    ('parcel_damaged',      'Parcel damaged'),
    ('access_restricted',   'Access restricted'),
    ('fraud_suspected',     'Fraud suspected'),
    ('other',               'Other'),
)


class FailedDelivery(models.Model):
    id = models.BigAutoField(primary_key=True)
    tracking_number = models.CharField(max_length=80, db_index=True)
    order_id = models.CharField(max_length=64, db_index=True)
    reason = models.CharField(max_length=24, choices=FAILED_DELIVERY_REASON_CHOICES)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    notes = models.TextField(blank=True, default='')
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(
        max_length=24, blank=True, default='',
        choices=(('redeliver', 'Redeliver'),
                 ('reschedule', 'Reschedule'),
                 ('return_to_sender', 'Return to sender'),
                 ('hold_at_pickup_point', 'Hold at pickup point'),
                 ('refund', 'Refund issued')),
    )
    occurred_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH19 — Customs exceptions
# ─────────────────────────────────────────────────────────────────

class CustomsException(models.Model):
    id = models.BigAutoField(primary_key=True)
    tracking_number = models.CharField(max_length=80, db_index=True)
    declaration = models.ForeignKey(
        CustomsDeclaration, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exceptions',
    )
    kind = models.CharField(
        max_length=24,
        choices=(('held_for_inspection', 'Held for inspection'),
                 ('missing_paperwork', 'Missing paperwork'),
                 ('value_disputed', 'Value disputed'),
                 ('prohibited_goods', 'Prohibited goods'),
                 ('duty_unpaid', 'Duty unpaid')),
    )
    description = models.TextField(blank=True, default='')
    requires_buyer_action = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH20 — Fulfilment exceptions
# ─────────────────────────────────────────────────────────────────

class FulfilmentException(models.Model):
    id = models.BigAutoField(primary_key=True)
    order_id = models.CharField(max_length=64, db_index=True)
    tracking_number = models.CharField(max_length=80, blank=True, default='', db_index=True)
    kind = models.CharField(
        max_length=24,
        choices=(('damaged_in_transit', 'Damaged in transit'),
                 ('lost_in_transit', 'Lost in transit'),
                 ('mis_shipped', 'Mis-shipped'),
                 ('partial_shipment', 'Partial shipment'),
                 ('wrong_item', 'Wrong item delivered')),
    )
    severity = models.PositiveSmallIntegerField(default=5)
    description = models.TextField(blank=True, default='')
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_fulfilment_exceptions',
    )
    resolution = models.CharField(
        max_length=24, blank=True, default='',
        choices=(('reship', 'Reship'), ('refund', 'Refund'),
                 ('partial_refund', 'Partial refund'),
                 ('replacement', 'Replacement sent'),
                 ('credit', 'Store credit'),
                 ('insurance_claim', 'Insurance claim')),
    )
    resolved = models.BooleanField(default=False)
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH21 — Pickup points & lockers
# ─────────────────────────────────────────────────────────────────

class PickupPoint(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=160)
    carrier = models.ForeignKey(Carrier, on_delete=models.CASCADE, related_name='pickup_points')
    address = models.JSONField(default=dict)
    coords = models.JSONField(default=dict, blank=True)
    country = models.CharField(max_length=2, db_index=True)
    city = models.CharField(max_length=80, blank=True, default='')
    kind = models.CharField(
        max_length=12, default='store',
        choices=(('store', 'Partner store'),
                 ('locker', 'Locker'),
                 ('depot', 'Carrier depot')),
    )
    capacity = models.PositiveIntegerField(default=50)
    current_load = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    opening_hours = models.JSONField(default=dict, blank=True)


class PickupPointDelivery(models.Model):
    id = models.BigAutoField(primary_key=True)
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.PROTECT, related_name='deliveries')
    order_id = models.CharField(max_length=64, db_index=True)
    tracking_number = models.CharField(max_length=80, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pickup_deliveries')
    pickup_code = models.CharField(max_length=12)
    status = models.CharField(
        max_length=16, default='in_transit',
        choices=(('in_transit', 'In transit'),
                 ('ready', 'Ready for pickup'),
                 ('picked_up', 'Picked up'),
                 ('expired', 'Expired — returned')),
    )
    deadline_at = models.DateTimeField()
    notified_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Choice / local fulfilment
# ─────────────────────────────────────────────────────────────────

class ChoiceLocalFulfilment(models.Model):
    """One row per Choice-Local order. Tracks the domestic last-mile
    handoff inside Angola (or other Choice markets)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    warehouse_code = models.CharField(max_length=20, db_index=True)
    domestic_carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT, related_name='choice_fulfilments')
    promise_window_hours = models.PositiveSmallIntegerField(default=72)
    pick_to_dispatch_target_minutes = models.PositiveSmallIntegerField(default=240)
    actual_pick_to_dispatch_minutes = models.PositiveIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)
    sla_met = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH23 — Compliance rules
# ─────────────────────────────────────────────────────────────────

class ComplianceRule(models.Model):
    """Country-specific rule that gates cross-border shipping —
    e.g. EU IOSS VAT < 150 EUR, USA Section 321 < 800 USD,
    Brazil import limit, Angola customs clearance docs."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=160)
    sender_country = models.CharField(max_length=2, blank=True, default='', db_index=True)
    recipient_country = models.CharField(max_length=2, db_index=True)
    rule_kind = models.CharField(
        max_length=24,
        choices=(('value_threshold', 'Value threshold'),
                 ('category_block', 'Category prohibited'),
                 ('docs_required', 'Documents required'),
                 ('eori_required', 'EORI required'),
                 ('vat_registration', 'VAT registration required'),
                 ('ioss_required', 'IOSS required')),
    )
    config = models.JSONField(default=dict)
    enforcement = models.CharField(
        max_length=12, default='block',
        choices=(('block', 'Block shipment'),
                 ('warn', 'Warn seller'),
                 ('require_docs', 'Require additional docs')),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — Logistics KPI snapshot
# ─────────────────────────────────────────────────────────────────

class LogisticsKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    shipments_created = models.PositiveIntegerField(default=0)
    shipments_delivered = models.PositiveIntegerField(default=0)
    avg_transit_days = models.FloatField(default=0)
    on_time_pct = models.FloatField(default=0)
    delivery_success_pct = models.FloatField(default=0)
    failed_delivery_count = models.PositiveIntegerField(default=0)
    customs_held_count = models.PositiveIntegerField(default=0)
    insurance_claim_count = models.PositiveIntegerField(default=0)
    cod_collected_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cod_pending_count = models.PositiveIntegerField(default=0)
    return_count = models.PositiveIntegerField(default=0)
    pickup_point_usage_pct = models.FloatField(default=0)
    fulfilment_exception_count = models.PositiveIntegerField(default=0)
    avg_label_gen_seconds = models.FloatField(default=0)
    by_carrier = models.JSONField(default=dict, blank=True)
    by_destination = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class LogisticsEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64, db_index=True)
    tracking_number = models.CharField(max_length=80, blank=True, default='', db_index=True)
    order_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='logistics_events',
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='emitted_logistics_events',
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, kind, tracking_number='', order_id='',
            seller=None, actor=None, payload=None):
        try:
            return LogisticsEvent.objects.create(
                kind=kind, tracking_number=tracking_number[:80],
                order_id=order_id[:64], seller=seller, actor=actor,
                payload=payload or {},
            )
        except Exception:
            return None
