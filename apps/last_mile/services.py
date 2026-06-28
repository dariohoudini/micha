"""
Last-mile services — Angola delivery algorithms.

Chapter → function map:
  CH2   seed_zones / get_zone / calculate_shipping_rate
  CH3   create_gps_address / address_quality_score
  CH4   assign_courier (scoring) / schedule_reassignment
  CH5   optimise_route (nearest-neighbour + 2-opt, haversine)
  CH6   capture_pod / generate_pod_otp / verify_pod_otp
  CH7   handle_delivery_failure (FAILURE_ACTIONS) / initiate_return
  CH8   available_windows / reschedule_window
  CH10  detect_consolidations / can_consolidate / consolidate
  CH11  handle_weight_discrepancy
  CH13  ingest_tracking_event (normalise + notify)
  CH20  recompute_courier_score
  CH24  snapshot_kpis
"""
import math
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from . import provinces as pv
from .models import (
    Courier, DeliveryRoute, GpsDeliveryAddress, LastMileEvent,
    LastMileKpiSnapshot, LastMileShipment, PackageConsolidation,
    ProofOfDelivery, ProvinceZone, RouteStop, ShipmentEvent,
    WeightDiscrepancy,
)

MAX_DELIVERY_ATTEMPTS = 3
WEIGHT_TOLERANCE_PCT = 5
PROXIMITY_RADIUS_M = 200
COD_REFUSAL_DISABLE = 2

# CH7 failure → recovery action
FAILURE_ACTIONS = {
    'not_home': 'reattempt_next_day',
    'wrong_address': 'contact_buyer_first',
    'cod_refused': 'return_immediately',
    'cod_unavailable': 'reattempt_next_day',
    'access_blocked': 'reattempt_next_day',
    'buyer_cancelled': 'return_immediately',
    'package_damaged': 'return_immediately',
}


# ──────────────────────────────────────────────────────────────────────
# CH2 — Zones + rate calculation
# ──────────────────────────────────────────────────────────────────────

def seed_zones(origin='Luanda'):
    """Seed the matrix for `origin` to all 18 provinces (doc CH2)."""
    created = 0
    for dest in pv.PROVINCES:
        zc = (pv.SAME_CITY if dest == origin
              else pv.classify_zone(origin, dest))
        rates = pv.ZONE_RATES[zc]
        _, was = ProvinceZone.objects.get_or_create(
            origin_province=origin, destination_province=dest,
            defaults={'zone_class': zc, 'base_rate_cents': rates['base'],
                      'rate_per_kg_cents': rates['per_kg'],
                      'transit_days_min': rates['days'][0],
                      'transit_days_max': rates['days'][1],
                      'cod_available': pv.cod_available(dest)})
        created += 1 if was else 0
    return {'created': created}


def get_zone(origin, destination):
    zone = ProvinceZone.objects.filter(
        origin_province=origin, destination_province=destination).first()
    if zone:
        return zone
    # On-the-fly classification for an un-seeded pair (doc CH2 fallback).
    zc = (pv.SAME_CITY if origin == destination
          else pv.classify_zone(origin, destination))
    rates = pv.ZONE_RATES[zc]
    return ProvinceZone.objects.create(
        origin_province=origin, destination_province=destination,
        zone_class=zc, base_rate_cents=rates['base'],
        rate_per_kg_cents=rates['per_kg'], transit_days_min=rates['days'][0],
        transit_days_max=rates['days'][1],
        cod_available=pv.cod_available(destination))


class CODNotAvailable(Exception):
    pass


def calculate_shipping_rate(origin, destination, *, weight_grams,
                            length_cm=0, width_cm=0, height_cm=0,
                            payment_method='prepaid',
                            free_shipping=False, divisor=pv.VOLUMETRIC_DIVISOR):
    """Per-shipment rate (doc CH2.2): chargeable = max(actual, volumetric),
    + COD surcharge, × remote multiplier. Returns (rate_cents, zone).
    """
    zone = get_zone(origin, destination)
    dim_weight_grams = (
        float(length_cm) * float(width_cm) * float(height_cm)
        / divisor * 1000) if (length_cm and width_cm and height_cm) else 0
    chargeable_grams = max(weight_grams, dim_weight_grams)
    chargeable_kg = chargeable_grams / 1000
    rate = (0 if free_shipping
            else zone.base_rate_cents
            + math.ceil(chargeable_kg) * zone.rate_per_kg_cents)
    if zone.zone_class == pv.REMOTE and not free_shipping:
        rate = int(rate * pv.REMOTE_MULTIPLIER)
    if payment_method == 'cod':
        if not zone.cod_available:
            raise CODNotAvailable(destination)
        rate += pv.COD_SURCHARGE_CENTS  # COD surcharge even if free shipping
    return rate, zone


# ──────────────────────────────────────────────────────────────────────
# CH3 — GPS-pin addresses + quality score
# ──────────────────────────────────────────────────────────────────────

def address_quality_score(addr):
    """0-100 internal score for courier-assignment priority (doc CH3)."""
    score = 0
    if addr.latitude is not None and addr.longitude is not None:
        score += 30
    if addr.landmark and len(addr.landmark) >= 50:
        score += 20
    elif addr.landmark and len(addr.landmark) >= 20:
        score += 10
    if addr.bairro:
        score += 20
    if addr.phone_number:
        score += 20
    if addr.verified_by_delivery:
        score += 10
    return min(100, score)


def create_gps_address(buyer, *, province, landmark, phone_number,
                       latitude=None, longitude=None, municipio='', bairro='',
                       delivery_notes='', label='Casa', is_default=False):
    if province not in pv.PROVINCES:
        raise ValueError('invalid province')
    if not landmark or len(landmark) < 20:
        raise ValueError('landmark required (min 20 chars)')
    if latitude is None or longitude is None:
        raise ValueError('GPS pin required')
    addr = GpsDeliveryAddress(
        buyer=buyer, province=province, municipio=municipio, bairro=bairro,
        landmark=landmark, phone_number=phone_number, latitude=latitude,
        longitude=longitude, delivery_notes=delivery_notes, label=label,
        is_default=is_default)
    addr.quality_score = address_quality_score(addr)
    addr.save()
    if is_default:
        GpsDeliveryAddress.objects.filter(buyer=buyer).exclude(
            id=addr.id).update(is_default=False)
    return addr


# ──────────────────────────────────────────────────────────────────────
# CH4 — Courier assignment
# ──────────────────────────────────────────────────────────────────────

def _haversine_km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return 0.0
    r = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lng2) - float(lng1))
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


MAX_PROXIMITY_KM = 50.0


@transaction.atomic
def assign_courier(shipment):
    """Match a shipment to the best available courier (doc CH4)."""
    candidates = list(Courier.objects.select_for_update().filter(
        status='available', province=shipment.origin_province))
    # capacity
    candidates = [c for c in candidates
                  if c.today_assigned_count < c.max_daily_deliveries]
    # vehicle vs weight
    if shipment.weight_declared_grams > pv.MOTORBIKE_MAX_GRAMS:
        candidates = [c for c in candidates
                      if c.vehicle_type in ('car', 'van', 'truck')]
    # COD float headroom + bonded
    if shipment.cod_amount_cents > 0:
        candidates = [c for c in candidates
                      if c.security_bonded
                      and c.current_cod_float_cents + shipment.cod_amount_cents
                      <= c.max_cod_float_cents]
    if not candidates:
        schedule_reassignment(shipment)
        return None

    wh_lat = shipment.address.latitude if shipment.address else None
    wh_lng = shipment.address.longitude if shipment.address else None

    def score(c):
        proximity = _haversine_km(c.current_lat, c.current_lng, wh_lat, wh_lng)
        load = c.today_assigned_count / max(1, c.max_daily_deliveries)
        return (float(c.performance_score) * 0.40
                + (1 - min(1.0, proximity / MAX_PROXIMITY_KM)) * 30
                + (1 - load) * 20
                + (10 if not c.has_cod_today else 0))

    best = max(candidates, key=score)
    shipment.courier = best
    shipment.status = 'assigned'
    shipment.save(update_fields=['courier', 'status', 'updated_at'])
    best.today_assigned_count += 1
    best.current_cod_float_cents += shipment.cod_amount_cents
    if shipment.cod_amount_cents > 0:
        best.has_cod_today = True
    best.save(update_fields=['today_assigned_count', 'current_cod_float_cents',
                             'has_cod_today'])
    _log_event(shipment, 'pending', 'courier assigned',
               source='manual')
    LastMileEvent.log('courier_assigned', shipment_id=str(shipment.id),
                      courier_id=str(best.id))
    return best


def schedule_reassignment(shipment, *, delay_minutes=30):
    LastMileEvent.log('reassignment_scheduled', shipment_id=str(shipment.id),
                      delay_minutes=delay_minutes)


# ──────────────────────────────────────────────────────────────────────
# CH5 — Route optimisation
# ──────────────────────────────────────────────────────────────────────

def _route_distance(points):
    total = 0.0
    for i in range(len(points) - 1):
        total += _haversine_km(points[i][0], points[i][1],
                               points[i + 1][0], points[i + 1][1])
    return total


def _two_opt(stops, start):
    """2-opt swap to remove crossings (doc CH5)."""
    def coords(seq):
        return [start] + [(s['lat'], s['lng']) for s in seq]
    best = stops[:]
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if _route_distance(coords(candidate)) < _route_distance(
                        coords(best)) - 1e-9:
                    best = candidate
                    improved = True
    return best


def optimise_route(courier, route_date=None):
    """Nearest-neighbour + 2-opt over the courier's assigned shipments for
    the date, honouring morning/afternoon windows (doc CH5).
    """
    route_date = route_date or timezone.now().date()
    shipments = list(LastMileShipment.objects.filter(
        courier=courier, status__in=('assigned', 'picked_up', 'out_for_delivery'),
        scheduled_date=route_date).select_related('address'))
    stops = []
    for s in shipments:
        if s.address and s.address.latitude is not None:
            stops.append({'shipment': s, 'lat': float(s.address.latitude),
                          'lng': float(s.address.longitude),
                          'window': s.time_window,
                          'cod': s.cod_amount_cents})
    if not stops:
        return None
    start = (float(courier.current_lat) if courier.current_lat else stops[0]['lat'],
             float(courier.current_lng) if courier.current_lng else stops[0]['lng'])

    # Nearest-neighbour, morning windows first.
    def window_rank(w):
        return {'morning': 0, 'all_day': 1, 'afternoon': 2, 'evening': 3}.get(w, 1)

    unvisited = sorted(stops, key=lambda s: window_rank(s['window']))
    route = []
    pos = start
    while unvisited:
        # prefer same-or-earlier window, then nearest
        cur_rank = window_rank(unvisited[0]['window'])
        avail = [s for s in unvisited if window_rank(s['window']) <= cur_rank] \
            or unvisited
        nearest = min(avail, key=lambda s: _haversine_km(
            pos[0], pos[1], s['lat'], s['lng']))
        route.append(nearest)
        unvisited.remove(nearest)
        pos = (nearest['lat'], nearest['lng'])

    route = _two_opt(route, start)

    with transaction.atomic():
        dr, _ = DeliveryRoute.objects.update_or_create(
            courier=courier, route_date=route_date,
            defaults={'total_stops': len(route)})
        dr.stops.all().delete()
        prev = start
        total = 0.0
        for seq, stop in enumerate(route, 1):
            leg = _haversine_km(prev[0], prev[1], stop['lat'], stop['lng'])
            total += leg
            RouteStop.objects.create(route=dr, shipment=stop['shipment'],
                                     sequence=seq,
                                     leg_distance_km=Decimal(str(round(leg, 2))))
            prev = (stop['lat'], stop['lng'])
        dr.total_distance_km = Decimal(str(round(total, 2)))
        dr.save(update_fields=['total_distance_km', 'total_stops'])
    return dr


# ──────────────────────────────────────────────────────────────────────
# CH6 — Proof of delivery
# ──────────────────────────────────────────────────────────────────────

def generate_pod_otp(shipment):
    otp = f'{secrets.randbelow(900000) + 100000}'
    pod, _ = ProofOfDelivery.objects.get_or_create(shipment=shipment)
    pod.otp_code = otp
    pod.save(update_fields=['otp_code'])
    return otp


@transaction.atomic
def capture_pod(shipment, *, photo_key='', otp_entered='', signature_key='',
                cod_collected_cents=0, lat=None, lng=None, offline=False):
    """Courier submits POD at handoff (doc CH6). Photo required. OTP primary,
    signature fallback. On success → delivered + escrow/COD bridge.
    """
    if not photo_key and not offline:
        return {'ok': False, 'reason': 'photo_required'}
    pod, _ = ProofOfDelivery.objects.get_or_create(shipment=shipment)
    pod.photo_key = photo_key
    pod.signature_key = signature_key
    pod.cod_collected_cents = cod_collected_cents
    pod.delivery_lat = lat
    pod.delivery_lng = lng
    pod.captured_offline = offline
    pod.delivered_at = timezone.now()
    # OTP verify (primary), else signature must be present (fallback)
    if otp_entered and pod.otp_code and otp_entered == pod.otp_code:
        pod.otp_verified = True
    elif not signature_key:
        return {'ok': False, 'reason': 'otp_or_signature_required'}
    # proximity check (200m of pin)
    if lat is not None and shipment.address and shipment.address.latitude:
        dist = _haversine_km(lat, lng, shipment.address.latitude,
                             shipment.address.longitude)
        pod.proximity_ok = dist * 1000 <= PROXIMITY_RADIUS_M
    pod.save()

    shipment.status = 'delivered'
    shipment.actual_delivery_at = timezone.now()
    shipment.save(update_fields=['status', 'actual_delivery_at', 'updated_at'])
    _log_event(shipment, 'delivered', 'POD captured')
    # Address verified after successful delivery (doc CH10 / JOB 10)
    if shipment.address:
        GpsDeliveryAddress.objects.filter(id=shipment.address_id).update(
            verified_by_delivery=True)

    # Bridge: COD collection → payments_angola; else escrow release signal.
    if shipment.cod_amount_cents > 0:
        _bridge_cod_collected(shipment, cod_collected_cents)
    LastMileEvent.log('pod_captured', shipment_id=str(shipment.id),
                      otp=pod.otp_verified, cod=cod_collected_cents)
    return {'ok': True, 'otp_verified': pod.otp_verified,
            'proximity_ok': pod.proximity_ok}


def _bridge_cod_collected(shipment, amount_cents):
    try:
        from apps.payments_angola import services as pa
        from apps.payments_angola.models import PaymentFlow
        flow = PaymentFlow.objects.filter(
            order_id=shipment.order_id, method='cod').first()
        if flow and shipment.courier and shipment.courier.user:
            pa.collect_cod(flow, courier=shipment.courier.user,
                           proof_key=shipment.pod.photo_key)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH7 — Failed delivery
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def handle_delivery_failure(shipment, *, failure_type, notes=''):
    shipment.status = 'failed'
    shipment.failure_type = failure_type
    shipment.failure_count += 1
    shipment.save(update_fields=['status', 'failure_type', 'failure_count',
                                 'updated_at'])
    _log_event(shipment, 'failed_attempt', f'{failure_type}: {notes}'[:200])
    # Bridge to logistics_ops.FailedDelivery for the ops queue.
    try:
        from apps.logistics_ops.models import FailedDelivery
        FailedDelivery.objects.create(
            tracking_number=shipment.micha_tracking_id,
            order_id=shipment.order_id,
            reason=failure_type if failure_type in (
                'not_home', 'wrong_address', 'cod_refused',
                'cod_unavailable', 'access_blocked') else 'other',
            attempt_number=shipment.failure_count, notes=notes)
    except Exception:
        pass
    # COD refusal → buyer COD profile (bridge)
    if failure_type == 'cod_refused':
        _bridge_cod_refusal(shipment)

    if shipment.failure_count >= MAX_DELIVERY_ATTEMPTS:
        return initiate_return(shipment, reason='max_attempts')

    action = FAILURE_ACTIONS.get(failure_type, 'reattempt_next_day')
    if action == 'return_immediately':
        return initiate_return(shipment, reason=failure_type)
    elif action == 'reattempt_next_day':
        shipment.scheduled_date = timezone.now().date() + timedelta(days=1)
        shipment.status = 'assigned'
        shipment.save(update_fields=['scheduled_date', 'status'])
        return {'action': 'reattempt_next_day'}
    else:  # contact_buyer_first (wrong_address)
        if shipment.address:
            GpsDeliveryAddress.objects.filter(id=shipment.address_id).update(
                needs_pin_reverification=True)
        return {'action': 'contact_buyer_first'}


def initiate_return(shipment, *, reason=''):
    shipment.status = 'returning'
    shipment.save(update_fields=['status', 'updated_at'])
    _log_event(shipment, 'returning', f'return: {reason}')
    LastMileEvent.log('return_initiated', shipment_id=str(shipment.id),
                      reason=reason)
    return {'action': 'return_to_warehouse'}


def _bridge_cod_refusal(shipment):
    try:
        from apps.payments_angola.models import BuyerCodProfile
        addr = shipment.address
        buyer = addr.buyer if addr else None
        if buyer:
            profile, _ = BuyerCodProfile.objects.get_or_create(buyer=buyer)
            profile.refusal_count_90d += 1
            profile.total_refusals += 1
            if profile.refusal_count_90d >= COD_REFUSAL_DISABLE:
                profile.cod_disabled = True
                profile.cod_disabled_reason = 'COD refused at doorstep'
            profile.save()
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH8 — Time windows
# ──────────────────────────────────────────────────────────────────────

def available_windows(origin, destination, *, requested_date=None):
    zone = get_zone(origin, destination)
    slots = ['all_day']
    if zone.zone_class == pv.SAME_CITY:
        slots += ['morning', 'afternoon']
    return slots


def reschedule_window(shipment, *, window, new_date=None):
    if shipment.status in ('out_for_delivery', 'delivered'):
        return {'ok': False, 'reason': 'too_late'}
    shipment.time_window = window
    if new_date:
        shipment.scheduled_date = new_date
    shipment.save(update_fields=['time_window', 'scheduled_date', 'updated_at'])
    return {'ok': True}


# ──────────────────────────────────────────────────────────────────────
# CH10 — Consolidation
# ──────────────────────────────────────────────────────────────────────

MAX_SINGLE_SHIPMENT_GRAMS = 30_000


def can_consolidate(shipments):
    if len({s.address_id for s in shipments}) != 1:
        return False
    if len({s.origin_province for s in shipments}) != 1:
        return False
    if any(s.status not in ('pending', 'ready') for s in shipments):
        return False
    if sum(s.weight_declared_grams for s in shipments) > MAX_SINGLE_SHIPMENT_GRAMS:
        return False
    if len({bool(s.cod_amount_cents) for s in shipments}) > 1:
        return False
    return True


@transaction.atomic
def consolidate(shipments, *, buyer=None, seller=None):
    if not can_consolidate(shipments):
        return None
    first = shipments[0]
    combined_weight = sum(s.weight_declared_grams for s in shipments)
    combined_cod = sum(s.cod_amount_cents for s in shipments)
    rate, _ = calculate_shipping_rate(
        first.origin_province, first.destination_province,
        weight_grams=combined_weight,
        payment_method='cod' if combined_cod else 'prepaid')
    con = PackageConsolidation.objects.create(
        buyer=buyer or (first.address.buyer if first.address else None),
        seller=seller or first.seller, destination_address=first.address,
        combined_weight_grams=combined_weight, combined_cod_cents=combined_cod,
        combined_rate_cents=rate,
        original_rate_total_cents=sum(s.shipping_rate_cents for s in shipments),
        micha_tracking_id=_gen_tracking(), status='accepted')
    for s in shipments:
        s.consolidation = con
        s.save(update_fields=['consolidation'])
    LastMileEvent.log('consolidated', consolidation_id=con.id,
                      children=len(shipments))
    return con


# ──────────────────────────────────────────────────────────────────────
# CH11 — Weight discrepancy
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def handle_weight_discrepancy(shipment, actual_grams):
    declared = shipment.weight_declared_grams or 1
    shipment.weight_actual_grams = actual_grams
    shipment.save(update_fields=['weight_actual_grams'])
    delta = actual_grams - declared
    delta_pct = delta / declared * 100
    if abs(delta_pct) <= WEIGHT_TOLERANCE_PCT:
        return {'severity': 'within_tolerance', 'delta_pct': round(delta_pct, 2)}

    correct_rate, _ = calculate_shipping_rate(
        shipment.origin_province, shipment.destination_province,
        weight_grams=actual_grams,
        length_cm=shipment.length_cm, width_cm=shipment.width_cm,
        height_cm=shipment.height_cm)
    shortfall = correct_rate - shipment.shipping_rate_cents

    if shortfall <= 0:
        severity = 'overdeclared'
    elif delta_pct <= 20:
        severity = 'minor'
    else:
        # major; escalate to 'fraud' if repeated
        recent_majors = WeightDiscrepancy.objects.filter(
            seller=shipment.seller, severity__in=('major', 'fraud'),
            created_at__gte=timezone.now() - timedelta(days=90)).count()
        severity = 'fraud' if recent_majors >= 2 else 'major'

    wd = WeightDiscrepancy.objects.create(
        shipment=shipment, seller=shipment.seller, declared_grams=declared,
        actual_grams=actual_grams, delta_grams=delta,
        delta_pct=Decimal(str(round(delta_pct, 2))), severity=severity,
        shortfall_cents=max(0, shortfall))
    # Bridge: deduct shortfall from seller payout (seller_tools/accounting).
    if shortfall > 0:
        _bridge_payout_deduction(shipment.seller, shortfall, shipment.order_id)
    LastMileEvent.log('weight_discrepancy', shipment_id=str(shipment.id),
                      severity=severity, shortfall=max(0, shortfall))
    return {'severity': severity, 'shortfall_cents': max(0, shortfall),
            'delta_pct': round(delta_pct, 2), 'id': wd.id}


def _bridge_payout_deduction(seller, amount_cents, order_id):
    try:
        from apps.accounting import services as acc
        acc.post_journal(
            entry_date=timezone.now().date(),
            description=f'Weight underdeclaration shortfall order {order_id}',
            lines=[{'account': '5010', 'debit': amount_cents},
                   {'account': '2020', 'credit': amount_cents,
                    'party': seller}],
            source_type='system_auto', source_id=order_id)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH13 — Tracking pipeline
# ──────────────────────────────────────────────────────────────────────

CARRIER_STATUS_MAP = {
    'AWAITING_PICKUP': 'pending', 'Aguarda Recolha': 'pending',
    'COLLECTED': 'picked_up', 'Recolhido': 'picked_up', 'IN_TRANSIT': 'in_transit',
    'HUB_SCAN': 'at_hub', 'OUT_OF_ORIGIN': 'in_transit',
    'OUT_FOR_DELIVERY': 'out_for_delivery', 'Em entrega': 'out_for_delivery',
    'DELIVERED': 'delivered', 'Entregue': 'delivered',
    'FAILED': 'failed_attempt', 'CUSTOMS_HOLD': 'exception',
}


def ingest_tracking_event(shipment, *, raw_status, source='carrier_webhook',
                          location=''):
    """Normalise a carrier event and update the buyer-facing timeline."""
    status = CARRIER_STATUS_MAP.get(raw_status, raw_status.lower()
                                    if raw_status.lower() in dict(
                                        ShipmentEvent.STATUS_CHOICES) else 'in_transit')
    ShipmentEvent.objects.create(
        shipment=shipment, status=status, raw_status=raw_status,
        location_description=location, source=source)
    # reflect onto shipment status for key transitions
    if status in ('picked_up', 'in_transit', 'out_for_delivery', 'delivered'):
        shipment.status = status if status != 'picked_up' else 'picked_up'
        if status == 'picked_up' and not shipment.picked_up_at:
            shipment.picked_up_at = timezone.now()
        shipment.save(update_fields=['status', 'picked_up_at', 'updated_at'])
    _notify_buyer_tracking(shipment, status)
    return status


def _log_event(shipment, status, location='', source='courier_app'):
    ShipmentEvent.objects.create(
        shipment=shipment, status=status, location_description=location[:200],
        source=source)


def _notify_buyer_tracking(shipment, status):
    messages = {
        'out_for_delivery': 'O seu pacote está a caminho!',
        'delivered': 'Pacote entregue com sucesso',
        'failed_attempt': 'Tentativa de entrega falhada',
        'exception': 'O seu pacote está retido — veja detalhes',
    }
    msg = messages.get(status)
    if not msg or not shipment.address:
        return
    try:
        from apps.notifications.push_service import send_to_user
        send_to_user(shipment.address.buyer, title='MICHA Express', body=msg)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH20 — Courier performance score
# ──────────────────────────────────────────────────────────────────────

def recompute_courier_score(courier, *, window_days=30):
    since = timezone.now() - timedelta(days=window_days)
    ships = LastMileShipment.objects.filter(courier=courier,
                                            created_at__gte=since)
    total = ships.count()
    if not total:
        return courier.performance_score
    delivered = ships.filter(status='delivered').count()
    on_time = ships.filter(
        status='delivered',
        actual_delivery_at__date__lte=models_eta()).count()
    pod_rate = ProofOfDelivery.objects.filter(
        shipment__courier=courier, shipment__created_at__gte=since,
        photo_key__gt='').count()
    success_rate = delivered / total
    score = (success_rate * 40 + (delivered / total) * 30
             + (pod_rate / max(1, delivered)) * 20 + 10)
    courier.performance_score = Decimal(str(round(min(100, score), 2)))
    courier.save(update_fields=['performance_score'])
    return courier.performance_score


def models_eta():
    return timezone.now().date()


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPIs
# ──────────────────────────────────────────────────────────────────────

def snapshot_kpis(snapshot_date=None):
    snapshot_date = snapshot_date or timezone.now().date()
    since = timezone.now() - timedelta(days=7)
    ships = LastMileShipment.objects.filter(created_at__gte=since)
    total = ships.count()
    delivered = ships.filter(status='delivered').count()
    first_attempt = ships.filter(status='delivered', failure_count=0).count()
    failed_buyer = ships.filter(
        status__in=('failed', 'returning'),
        failure_type__in=('not_home', 'cod_refused', 'cod_unavailable',
                          'wrong_address')).count()
    on_time = ships.filter(
        status='delivered',
        actual_delivery_at__date__lte=models_eta()).count()

    weighed = ships.exclude(weight_actual_grams=None).count()
    discrep = WeightDiscrepancy.objects.filter(
        created_at__gte=since, severity__in=('major', 'fraud')).count()

    snap, _ = LastMileKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'first_attempt_rate_pct': round(first_attempt / total * 100, 2)
            if total else 0,
            'delivery_success_pct': round(delivered / total * 100, 2)
            if total else 0,
            'on_time_pct': round(on_time / delivered * 100, 2)
            if delivered else 0,
            'failed_buyer_caused_pct': round(failed_buyer / total * 100, 2)
            if total else 0,
            'weight_discrepancy_pct': round(discrep / weighed * 100, 2)
            if weighed else 0,
            'active_couriers': Courier.objects.filter(
                status__in=('available', 'on_route')).count(),
            'by_province': dict(ships.values('destination_province').annotate(
                n=Count('id')).values_list('destination_province', 'n')),
        })
    return snap


def _gen_tracking():
    return f'MICHA{secrets.token_hex(7).upper()}'


# ──────────────────────────────────────────────────────────────────────
# Shipment creation (computes rate + EDD + tracking id)
# ──────────────────────────────────────────────────────────────────────

def create_shipment(*, order_id, seller, address, weight_grams,
                    length_cm=0, width_cm=0, height_cm=0,
                    payment_method='prepaid', cod_amount_cents=0,
                    time_window='all_day', origin_province='Luanda',
                    free_shipping=False):
    rate, zone = calculate_shipping_rate(
        origin_province, address.province, weight_grams=weight_grams,
        length_cm=length_cm, width_cm=width_cm, height_cm=height_cm,
        payment_method=payment_method, free_shipping=free_shipping)
    edd = timezone.now().date() + timedelta(days=zone.transit_days_max)
    shipment = LastMileShipment.objects.create(
        order_id=order_id, seller=seller, address=address,
        origin_province=origin_province,
        destination_province=address.province,
        micha_tracking_id=_gen_tracking(), weight_declared_grams=weight_grams,
        length_cm=Decimal(str(length_cm)), width_cm=Decimal(str(width_cm)),
        height_cm=Decimal(str(height_cm)), zone=zone,
        shipping_rate_cents=rate, cod_amount_cents=cod_amount_cents,
        time_window=time_window, estimated_delivery_date=edd, status='ready')
    _log_event(shipment, 'pending', 'shipment created', source='manual')
    return shipment
