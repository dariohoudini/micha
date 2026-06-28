"""
MICHA Last-Mile — Angola-specific delivery (human courier layer).

Source: MICHA_Logistics_Angola.docx (24 chapters). This app owns the
Angola-specific last-mile pieces that did not exist; the carrier-level
machinery (tracking normalisation, customs, SLA snapshots, pickup points,
returns) already lives in apps.logistics_ops and is bridged, not copied.

Chapters HERE:
  CH2   ProvinceZone (18-province matrix + rates)
  CH3   GpsDeliveryAddress (GPS pin + landmark + quality score)
  CH1/4/20 Courier, CourierApplication
  CH1   LastMileShipment, ShipmentEvent
  CH5   DeliveryRoute, RouteStop
  CH6   ProofOfDelivery
  CH10  PackageConsolidation
  CH11  WeightDiscrepancy
  CH24  LastMileKpiSnapshot

Bridged: logistics_ops (Carrier / ShippingLabel / TrackingNormalisedEvent /
FailedDelivery / PickupPoint / CarrierSlaSnapshot / CustomsDeclaration /
CodRemittance), payments_angola (COD), accounting (fee/cost), seller_tools.
"""
import uuid

from django.conf import settings
from django.db import models

from .provinces import ZONE_CLASS_CHOICES

User = settings.AUTH_USER_MODEL


# ──────────────────────────────────────────────────────────────────────
# CH2 — 18-province zone matrix
# ──────────────────────────────────────────────────────────────────────

class ProvinceZone(models.Model):
    origin_province = models.CharField(max_length=40, db_index=True)
    destination_province = models.CharField(max_length=40, db_index=True)
    zone_class = models.CharField(max_length=14, choices=ZONE_CLASS_CHOICES)
    base_rate_cents = models.IntegerField()
    rate_per_kg_cents = models.IntegerField()
    transit_days_min = models.PositiveSmallIntegerField(default=1)
    transit_days_max = models.PositiveSmallIntegerField(default=5)
    cod_available = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('origin_province', 'destination_province')]

    def __str__(self):
        return f'{self.origin_province}→{self.destination_province} ({self.zone_class})'


# ──────────────────────────────────────────────────────────────────────
# CH3 — GPS-pin / landmark delivery address
# ──────────────────────────────────────────────────────────────────────

class GpsDeliveryAddress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='gps_addresses')
    label = models.CharField(max_length=100, default='Casa')  # Casa/Trabalho
    province = models.CharField(max_length=40, db_index=True)
    municipio = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    landmark = models.TextField()  # required (doc CH3)
    address_line = models.TextField(blank=True)  # formal, often blank
    latitude = models.DecimalField(max_digits=10, decimal_places=8,
                                   null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8,
                                    null=True, blank=True)
    phone_number = models.CharField(max_length=20)
    delivery_notes = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    verified_by_delivery = models.BooleanField(default=False)
    quality_score = models.PositiveSmallIntegerField(default=0)  # 0-100
    needs_pin_reverification = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['buyer', 'is_default'])]


# ──────────────────────────────────────────────────────────────────────
# CH1 / CH4 / CH20 — Courier (the human last-mile rider)
# ──────────────────────────────────────────────────────────────────────

VEHICLE_CHOICES = [
    ('motorbike', 'Motorbike'), ('bicycle', 'Bicycle'), ('car', 'Car'),
    ('van', 'Van'), ('truck', 'Truck'),
]


class Courier(models.Model):
    STATUS_CHOICES = [('available', 'Available'), ('on_route', 'On route'),
                      ('off_duty', 'Off duty'), ('suspended', 'Suspended')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='courier_profile')
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=20)
    nif = models.CharField(max_length=32, blank=True)
    province = models.CharField(max_length=40, db_index=True)
    vehicle_type = models.CharField(max_length=12, choices=VEHICLE_CHOICES,
                                    default='motorbike')
    vehicle_registration = models.CharField(max_length=32, blank=True)
    active_zone_ids = models.JSONField(default=list, blank=True)  # ProvinceZone ids
    max_daily_deliveries = models.PositiveSmallIntegerField(default=20)
    max_cod_float_cents = models.BigIntegerField(default=50_000_000)  # 500k Kz
    current_cod_float_cents = models.BigIntegerField(default=0)
    today_assigned_count = models.PositiveSmallIntegerField(default=0)
    has_cod_today = models.BooleanField(default=False)
    current_lat = models.DecimalField(max_digits=10, decimal_places=8,
                                      null=True, blank=True)
    current_lng = models.DecimalField(max_digits=11, decimal_places=8,
                                      null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='off_duty', db_index=True)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2,
                                            default=70)  # 0-100
    security_bonded = models.BooleanField(default=False)  # COD-eligible
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['province', 'status'])]

    def __str__(self):
        return f'{self.full_name} ({self.vehicle_type})'


class CourierApplication(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'), ('docs_review', 'Docs review'),
        ('background_check', 'Background check'), ('training', 'Training'),
        ('test_delivery', 'Test delivery'), ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=20)
    nif = models.CharField(max_length=32, blank=True)
    province = models.CharField(max_length=40)
    vehicle_type = models.CharField(max_length=12, choices=VEHICLE_CHOICES)
    bi_document_key = models.CharField(max_length=300, blank=True)
    licence_key = models.CharField(max_length=300, blank=True)
    police_clearance_key = models.CharField(max_length=300, blank=True)
    bank_account = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default='submitted', db_index=True)
    test_deliveries_done = models.PositiveSmallIntegerField(default=0)
    courier = models.OneToOneField(Courier, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='application')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH1 — Last-mile shipment
# ──────────────────────────────────────────────────────────────────────

TIME_WINDOW_CHOICES = [
    ('morning', 'Morning 08-12'), ('afternoon', 'Afternoon 14-18'),
    ('all_day', 'All day'), ('evening', 'Evening 18-20'),
]
SHIPMENT_STATUS_CHOICES = [
    ('pending', 'Pending'), ('ready', 'Ready to ship'),
    ('assigned', 'Courier assigned'), ('picked_up', 'Picked up'),
    ('in_transit', 'In transit'), ('out_for_delivery', 'Out for delivery'),
    ('delivered', 'Delivered'), ('failed', 'Failed'),
    ('returning', 'Returning'), ('returned', 'Returned'),
]
FAILURE_TYPE_CHOICES = [
    ('not_home', 'Not home'), ('wrong_address', 'Wrong address'),
    ('cod_refused', 'COD refused'), ('cod_unavailable', 'COD unavailable'),
    ('access_blocked', 'Access blocked'), ('buyer_cancelled', 'Buyer cancelled'),
    ('package_damaged', 'Package damaged'),
]


class LastMileShipment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='last_mile_shipments')
    address = models.ForeignKey(GpsDeliveryAddress, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='shipments')
    courier = models.ForeignKey(Courier, on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='shipments')
    origin_province = models.CharField(max_length=40)
    destination_province = models.CharField(max_length=40)
    micha_tracking_id = models.CharField(max_length=24, unique=True)
    carrier_tracking_number = models.CharField(max_length=100, blank=True)
    weight_declared_grams = models.IntegerField(default=0)
    weight_actual_grams = models.IntegerField(null=True, blank=True)
    length_cm = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    width_cm = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    height_cm = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    zone = models.ForeignKey(ProvinceZone, on_delete=models.SET_NULL,
                             null=True, blank=True, related_name='+')
    shipping_rate_cents = models.IntegerField(default=0)
    cod_amount_cents = models.BigIntegerField(default=0)
    time_window = models.CharField(max_length=10, choices=TIME_WINDOW_CHOICES,
                                   default='all_day')
    scheduled_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=18, choices=SHIPMENT_STATUS_CHOICES,
                              default='pending', db_index=True)
    failure_count = models.PositiveSmallIntegerField(default=0)
    failure_type = models.CharField(max_length=16, choices=FAILURE_TYPE_CHOICES,
                                    blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    consolidation = models.ForeignKey('PackageConsolidation',
                                      on_delete=models.SET_NULL, null=True,
                                      blank=True, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'destination_province']),
            models.Index(fields=['courier', 'status']),
        ]


class ShipmentEvent(models.Model):
    """Normalised tracking timeline per shipment (doc CH13)."""
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('picked_up', 'Picked up'),
        ('at_hub', 'At hub'), ('in_transit', 'In transit'),
        ('out_for_delivery', 'Out for delivery'), ('delivered', 'Delivered'),
        ('failed_attempt', 'Failed attempt'), ('exception', 'Exception'),
        ('returning', 'Returning'),
    ]
    SOURCE_CHOICES = [
        ('courier_app', 'Courier app'), ('carrier_webhook', 'Carrier webhook'),
        ('carrier_poll', 'Carrier poll'), ('manual', 'Manual'),
    ]
    shipment = models.ForeignKey(LastMileShipment, on_delete=models.CASCADE,
                                 related_name='events')
    status = models.CharField(max_length=18, choices=STATUS_CHOICES,
                              db_index=True)
    raw_status = models.CharField(max_length=100, blank=True)
    location_description = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES,
                              default='courier_app')
    event_time = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['event_time']


# ──────────────────────────────────────────────────────────────────────
# CH5 — Route optimisation
# ──────────────────────────────────────────────────────────────────────

class DeliveryRoute(models.Model):
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE,
                                related_name='routes')
    route_date = models.DateField(db_index=True)
    total_stops = models.PositiveSmallIntegerField(default=0)
    total_distance_km = models.DecimalField(max_digits=8, decimal_places=2,
                                            default=0)
    optimised_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('courier', 'route_date')]


class RouteStop(models.Model):
    route = models.ForeignKey(DeliveryRoute, on_delete=models.CASCADE,
                              related_name='stops')
    shipment = models.ForeignKey(LastMileShipment, on_delete=models.CASCADE,
                                 related_name='route_stops')
    sequence = models.PositiveSmallIntegerField()
    leg_distance_km = models.DecimalField(max_digits=8, decimal_places=2,
                                          default=0)

    class Meta:
        ordering = ['sequence']
        unique_together = [('route', 'shipment')]


# ──────────────────────────────────────────────────────────────────────
# CH6 — Proof of delivery
# ──────────────────────────────────────────────────────────────────────

class ProofOfDelivery(models.Model):
    shipment = models.OneToOneField(LastMileShipment, on_delete=models.CASCADE,
                                    related_name='pod')
    photo_key = models.CharField(max_length=300, blank=True)
    otp_code = models.CharField(max_length=6, blank=True)  # server-generated
    otp_verified = models.BooleanField(default=False)
    signature_key = models.CharField(max_length=300, blank=True)
    cod_collected_cents = models.BigIntegerField(default=0)
    delivery_lat = models.DecimalField(max_digits=10, decimal_places=8,
                                       null=True, blank=True)
    delivery_lng = models.DecimalField(max_digits=11, decimal_places=8,
                                       null=True, blank=True)
    proximity_ok = models.BooleanField(default=True)  # within 200m of pin
    captured_offline = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)  # synced to server


# ──────────────────────────────────────────────────────────────────────
# CH10 — Package consolidation
# ──────────────────────────────────────────────────────────────────────

class PackageConsolidation(models.Model):
    STATUS_CHOICES = [('proposed', 'Proposed'), ('accepted', 'Accepted'),
                      ('declined', 'Declined'), ('dispatched', 'Dispatched')]
    buyer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='consolidations')
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='+')
    destination_address = models.ForeignKey(
        GpsDeliveryAddress, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')
    combined_weight_grams = models.IntegerField(default=0)
    combined_cod_cents = models.BigIntegerField(default=0)
    combined_rate_cents = models.IntegerField(default=0)
    original_rate_total_cents = models.IntegerField(default=0)
    micha_tracking_id = models.CharField(max_length=24, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='proposed', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH11 — Weight discrepancy
# ──────────────────────────────────────────────────────────────────────

class WeightDiscrepancy(models.Model):
    SEVERITY_CHOICES = [
        ('within_tolerance', 'Within tolerance'), ('minor', 'Minor'),
        ('major', 'Major'), ('fraud', 'Fraud pattern'),
        ('overdeclared', 'Over-declared (buyer credit)'),
    ]
    shipment = models.ForeignKey(LastMileShipment, on_delete=models.CASCADE,
                                 related_name='weight_discrepancies')
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='weight_discrepancies')
    declared_grams = models.IntegerField()
    actual_grams = models.IntegerField()
    delta_grams = models.IntegerField()
    delta_pct = models.DecimalField(max_digits=7, decimal_places=2)
    severity = models.CharField(max_length=18, choices=SEVERITY_CHOICES)
    shortfall_cents = models.IntegerField(default=0)  # deducted from payout
    disputed = models.BooleanField(default=False)
    seller_evidence_key = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

class LastMileKpiSnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    first_attempt_rate_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                 default=0)   # >85
    delivery_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                               default=0)     # >95
    on_time_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                      default=0)               # >88
    avg_transit_days_same_city = models.DecimalField(max_digits=5,
                                                     decimal_places=2,
                                                     default=0)
    failed_buyer_caused_pct = models.DecimalField(max_digits=5,
                                                  decimal_places=2, default=0)
    cod_acceptance_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                             default=0)        # >90
    weight_discrepancy_pct = models.DecimalField(max_digits=5,
                                                 decimal_places=2, default=0)
    avg_processing_hours = models.DecimalField(max_digits=7, decimal_places=2,
                                               default=0)
    active_couriers = models.IntegerField(default=0)
    by_province = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now=True)


class LastMileEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='last_mile_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            LastMileEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload)
        except Exception:
            pass
