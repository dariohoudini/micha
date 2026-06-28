"""
Logistics & Fulfilment Operations — domain services.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .carriers.registry import get_carrier_adapter
from .models import (
    AddressValidationResult, Carrier, CarrierService,
    CarrierSlaSnapshot, ChoiceLocalFulfilment, CodTransaction,
    ComplianceRule, CustomsDeclaration, CustomsException,
    DeliveryEtaSnapshot, DutyEstimate, FailedDelivery,
    FulfilmentException, FulfilmentWave, HSCodeAssignment,
    InboundShipmentItem, InsuranceClaim, LogisticsEvent,
    LogisticsKpiSnapshot, PackJob, ParcelInsurancePolicy,
    PickList, PickupPoint, PickupPointDelivery,
    ReverseLogisticsRecord, ReturnShipmentLabel, ShippingLabel,
    StockTransferOrder, TrackingNormalisedEvent,
    TrackingStatusUnified, WarehouseInboundShipment,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH2 — Carrier selection
# ═══════════════════════════════════════════════════════════════════

def select_best_service(*, from_country: str, to_country: str,
                         weight_kg: Decimal, declared_value: Decimal,
                         needs_ddp: bool = False, needs_cod: bool = False,
                         needs_dangerous: bool = False,
                         sla_class: str = 'standard') -> dict:
    """CH2.2 — rank by (capability fit, on_time_rate × health_score)
    over eligible carriers. Returns the best service + cheapest
    quote."""
    qs = Carrier.objects.filter(status='active')
    if needs_ddp:
        qs = qs.filter(supports_ddp=True)
    if needs_cod:
        qs = qs.filter(supports_cod=True)
    if needs_dangerous:
        qs = qs.filter(supports_dangerous_goods=True)
    candidates = []
    for c in qs:
        if c.country_scope and to_country.upper() not in [s.upper() for s in c.country_scope]:
            continue
        # Service filter by SLA class roughly.
        svc_qs = c.services.filter(is_active=True)
        if sla_class == 'rush':
            svc_qs = svc_qs.filter(service_type='express')
        elif sla_class == 'economy':
            svc_qs = svc_qs.filter(service_type__in=('economy', 'parcel_post', 'standard'))
        for svc in svc_qs:
            if weight_kg > svc.max_weight_kg:
                continue
            cost = svc.base_rate + svc.per_kg_rate * Decimal(str(weight_kg))
            score = c.on_time_rate * c.health_score / 100.0
            candidates.append({
                'carrier_code': c.code, 'service_id': svc.id,
                'service_code': svc.code, 'cost': cost,
                'currency': svc.currency, 'score': score,
                'min_days': svc.min_transit_days,
                'max_days': svc.max_transit_days,
            })
    if not candidates:
        return {'ok': False, 'code': 'NO_ELIGIBLE_CARRIER'}
    # Best = lowest cost / score ratio.
    candidates.sort(key=lambda c: (float(c['cost']) / max(c['score'], 0.01),
                                    c['max_days']))
    return {'ok': True, 'best': candidates[0], 'alternatives': candidates[1:5]}


# ═══════════════════════════════════════════════════════════════════
# CH3 — Label generation
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def generate_label(*, order_id: str, seller, carrier_code: str,
                    service_id: int, from_addr: dict, to_addr: dict,
                    weight_kg: Decimal, dimensions: dict,
                    declared_value: Decimal,
                    currency: str = 'AOA',
                    incoterm: str = 'DAP') -> ShippingLabel:
    carrier = Carrier.objects.get(code=carrier_code)
    service = CarrierService.objects.get(pk=service_id, carrier=carrier)
    adapter = get_carrier_adapter(carrier.code)
    response = adapter.create_label(
        service_code=service.code, from_addr=from_addr, to_addr=to_addr,
        weight_kg=weight_kg, dimensions=dimensions,
        declared_value=declared_value, incoterm=incoterm,
    )
    label = ShippingLabel.objects.create(
        order_id=order_id[:64], seller=seller, carrier=carrier,
        service=service, tracking_number=response.tracking_number,
        file_key=response.file_key, format=response.format,
        from_address=from_addr, to_address=to_addr,
        parcel_weight_kg=weight_kg, parcel_dimensions_cm=dimensions,
        declared_value=declared_value, currency=currency,
        status='generated' if response.success else 'failed',
        raw_response=response.raw or {},
    )
    # Bootstrap the unified tracking row so subsequent events can FK.
    TrackingStatusUnified.objects.update_or_create(
        tracking_number=label.tracking_number,
        defaults={
            'carrier': carrier, 'order_id': order_id[:64],
            'current_status': 'label_created',
            'last_event_at': timezone.now(),
        },
    )
    LogisticsEvent.log(
        kind='label.generated', tracking_number=label.tracking_number,
        order_id=order_id, seller=seller,
        payload={'carrier': carrier.code, 'service': service.code,
                 'declared_value': str(declared_value)},
    )
    return label


# ═══════════════════════════════════════════════════════════════════
# CH4 — Customs declaration + HS code
# ═══════════════════════════════════════════════════════════════════

def classify_hs_code(product_id: str, *, title: str = '',
                      category_id: str = '') -> dict:
    """ML stub — production hits a fine-tuned classifier. We do a
    cheap deterministic mapping by category, with confidence proxy."""
    existing = HSCodeAssignment.objects.filter(product_id=product_id).order_by('-confidence').first()
    if existing:
        return {'hs_code': existing.hs_code,
                'confidence': existing.confidence,
                'cached': True}
    # Deterministic fallback by category keyword.
    keyword_map = {
        'electronics': '8517',
        'clothing':    '6109',
        'shoes':       '6403',
        'beauty':      '3304',
        'food':        '2106',
        'toys':        '9503',
        'jewellery':   '7113',
        'home':        '9403',
    }
    key = (category_id or '').lower()
    hs = next((v for k, v in keyword_map.items() if k in key), '9999')
    confidence = 0.85 if hs != '9999' else 0.3
    obj = HSCodeAssignment.objects.create(
        product_id=product_id, hs_code=hs,
        confidence=confidence, classifier_version='v0_dev',
    )
    return {'hs_code': obj.hs_code, 'confidence': obj.confidence, 'cached': False}


@transaction.atomic
def generate_customs_declaration(*, label: ShippingLabel,
                                    items: list[dict],
                                    incoterm: str = 'DAP',
                                    eori_number: str = '') -> CustomsDeclaration:
    """`items` shape: [{product_id, qty, hs_code, value, currency, ...}]"""
    total = sum(Decimal(str(i.get('value', 0))) * Decimal(str(i.get('qty', 1))) for i in items)
    sender = label.from_address.get('country', '')
    recipient = label.to_address.get('country', '')
    decl = CustomsDeclaration.objects.create(
        label=label, sender_country=sender, recipient_country=recipient,
        incoterm=incoterm, items=items,
        declared_total_value=total, currency=label.currency,
        eori_number=eori_number[:40],
    )
    # Pre-compute duty estimate.
    duty = compute_duty_estimate(
        items=items, destination_country=recipient,
        incoterm=incoterm, currency=label.currency,
    )
    decl.duty_estimate_amount = duty['total_duty']
    decl.tax_estimate_amount = duty['total_vat']
    decl.save(update_fields=['duty_estimate_amount', 'tax_estimate_amount'])
    LogisticsEvent.log(
        kind='customs.declared', tracking_number=label.tracking_number,
        order_id=label.order_id, seller=label.seller,
        payload={'total': str(total), 'incoterm': incoterm,
                 'duty_estimate': str(decl.duty_estimate_amount)},
    )
    return decl


# ═══════════════════════════════════════════════════════════════════
# CH5 — Duty / landed cost
# ═══════════════════════════════════════════════════════════════════

# Simplified tariff table. Production loads from WCO + per-country
# tariff API; row shape: (hs_prefix, country) → (duty_pct, vat_pct).
_TARIFF_TABLE = {
    ('85', 'AO'): (Decimal('5'),  Decimal('14')),
    ('85', 'PT'): (Decimal('0'),  Decimal('23')),
    ('85', 'US'): (Decimal('0'),  Decimal('0')),
    ('61', 'AO'): (Decimal('15'), Decimal('14')),
    ('61', 'PT'): (Decimal('12'), Decimal('23')),
    ('64', 'AO'): (Decimal('15'), Decimal('14')),
    ('33', 'AO'): (Decimal('20'), Decimal('14')),
    ('21', 'AO'): (Decimal('10'), Decimal('14')),
    ('95', 'AO'): (Decimal('10'), Decimal('14')),
    ('94', 'AO'): (Decimal('10'), Decimal('14')),
}


def _lookup_tariff(hs_code: str, country: str) -> tuple[Decimal, Decimal]:
    if not hs_code:
        return Decimal('5'), Decimal('14')
    return _TARIFF_TABLE.get((hs_code[:2], country.upper()), (Decimal('5'), Decimal('14')))


def compute_duty_estimate(*, items: list[dict],
                            destination_country: str,
                            incoterm: str = 'DAP',
                            currency: str = 'USD') -> dict:
    total_duty = Decimal('0')
    total_vat = Decimal('0')
    per_item = []
    for it in items:
        value = Decimal(str(it.get('value', 0))) * Decimal(str(it.get('qty', 1)))
        hs = (it.get('hs_code') or '').strip()
        duty_pct, vat_pct = _lookup_tariff(hs, destination_country)
        duty = (value * duty_pct / Decimal(100)).quantize(Decimal('0.01'))
        vat = ((value + duty) * vat_pct / Decimal(100)).quantize(Decimal('0.01'))
        total_duty += duty
        total_vat += vat
        per_item.append({'hs_code': hs, 'duty_pct': str(duty_pct),
                          'vat_pct': str(vat_pct),
                          'duty_amount': str(duty),
                          'vat_amount': str(vat)})
        # Persist a cache row.
        if hs:
            DutyEstimate.objects.create(
                hs_code=hs, destination_country=destination_country.upper(),
                declared_value=value, currency=currency,
                duty_rate_pct=duty_pct, vat_rate_pct=vat_pct,
                duty_amount=duty, vat_amount=vat,
                landed_cost=(value + duty + vat),
                incoterm=incoterm,
                expires_at=timezone.now() + timedelta(hours=24),
            )
    landed = (sum(
        Decimal(str(i.get('value', 0))) * Decimal(str(i.get('qty', 1)))
        for i in items
    ) + total_duty + total_vat)
    return {'total_duty': total_duty.quantize(Decimal('0.01')),
            'total_vat': total_vat.quantize(Decimal('0.01')),
            'landed_cost': landed.quantize(Decimal('0.01')),
            'per_item': per_item, 'incoterm': incoterm,
            'currency': currency}


# ═══════════════════════════════════════════════════════════════════
# CH6 — Insurance
# ═══════════════════════════════════════════════════════════════════

def compute_insurance_premium(*, declared_value: Decimal,
                                coverage: str = 'loss_damage') -> Decimal:
    """Simple premium: 1.5% of declared value for loss+damage,
    2.5% for full (incl. delay). Minimum 100 AOA."""
    if coverage == 'full':
        pct = Decimal('2.5')
    else:
        pct = Decimal('1.5')
    return max(Decimal('100'),
                (Decimal(str(declared_value)) * pct / Decimal(100)).quantize(Decimal('0.01')))


def issue_insurance_policy(*, label: ShippingLabel,
                            declared_value: Decimal,
                            coverage: str = 'loss_damage',
                            valid_days: int = 60) -> ParcelInsurancePolicy:
    premium = compute_insurance_premium(declared_value=declared_value, coverage=coverage)
    return ParcelInsurancePolicy.objects.create(
        order_id=label.order_id, label=label,
        insured_amount=declared_value, premium_amount=premium,
        currency=label.currency, coverage=coverage,
        valid_until=timezone.now() + timedelta(days=valid_days),
    )


def file_insurance_claim(*, policy: ParcelInsurancePolicy,
                          claimant, reason: str,
                          claim_amount: Decimal,
                          description: str = '',
                          evidence_keys: list = None) -> InsuranceClaim:
    if policy.status != 'active':
        raise ValueError('POLICY_NOT_ACTIVE')
    obj = InsuranceClaim.objects.create(
        policy=policy, claimant=claimant, reason=reason,
        claim_amount=claim_amount, description=description[:5000],
        evidence_keys=evidence_keys or [],
    )
    policy.status = 'claimed'
    policy.save(update_fields=['status'])
    LogisticsEvent.log(
        kind='insurance.claim_filed',
        order_id=policy.order_id, seller=None,
        payload={'claim_id': str(obj.id), 'amount': str(claim_amount),
                 'reason': reason},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH7 — Tracking normalisation
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def ingest_tracking_event(*, tracking_number: str, carrier: Carrier,
                            raw_status: str, normalised_status: str,
                            occurred_at, carrier_event_id: str,
                            location: str = '',
                            raw_payload: dict = None,
                            classifier_confidence: float = 1.0) -> bool:
    """Idempotent on (tracking_number, carrier_event_id).
    Updates the unified status row + the buyer-facing ETA snapshot."""
    obj, created = TrackingNormalisedEvent.objects.get_or_create(
        tracking_number=tracking_number, carrier_event_id=carrier_event_id,
        defaults={
            'raw_status': raw_status[:80],
            'normalised_status': normalised_status,
            'classifier_confidence': classifier_confidence,
            'location': location[:120],
            'raw_payload': raw_payload or {},
            'occurred_at': occurred_at,
        },
    )
    if not created:
        return False
    # Propagate to the unified status row.
    state, _ = TrackingStatusUnified.objects.update_or_create(
        tracking_number=tracking_number,
        defaults={
            'carrier': carrier,
            'order_id': raw_payload.get('order_id', '') if raw_payload else '',
            'current_status': normalised_status,
            'last_event_at': occurred_at,
            'last_known_location': location[:120],
            'delivered_at': occurred_at if normalised_status == 'delivered' else None,
        },
    )
    # Refresh the ETA on relevant events.
    if normalised_status in ('picked_up', 'in_transit', 'customs_clearance',
                              'out_for_delivery'):
        refresh_eta_snapshot(tracking_number=tracking_number, state=state)
    LogisticsEvent.log(
        kind=f'tracking.{normalised_status}',
        tracking_number=tracking_number, payload={'location': location},
    )
    return True


# ═══════════════════════════════════════════════════════════════════
# CH8 — ETA engine
# ═══════════════════════════════════════════════════════════════════

def compute_eta(*, service: CarrierService, dispatched_at=None,
                 destination_country: str = '', signature_required: bool = False) -> dict:
    """Static estimate: dispatched + min..max transit days. Adjusts
    for known customs delays per country."""
    dispatched_at = dispatched_at or timezone.now()
    # CH8.1 customs adjustment.
    customs_adj_days = {
        'BR': 3, 'AR': 4, 'IN': 2, 'NG': 4, 'EG': 3,
    }.get((destination_country or '').upper(), 0)
    min_d = service.min_transit_days + customs_adj_days
    max_d = service.max_transit_days + customs_adj_days
    if signature_required:
        max_d += 1
    eta = dispatched_at + timedelta(days=max_d)
    return {'eta_at': eta, 'min_days': min_d, 'max_days': max_d,
            'confidence': 0.7}


def refresh_eta_snapshot(*, tracking_number: str,
                           state: TrackingStatusUnified = None) -> DeliveryEtaSnapshot:
    if not state:
        state = TrackingStatusUnified.objects.filter(tracking_number=tracking_number).first()
        if not state:
            return None
    # Reduce uncertainty as parcel progresses.
    confidence_map = {
        'picked_up': 0.7,
        'in_transit': 0.8,
        'customs_clearance': 0.6,
        'out_for_delivery': 0.95,
    }
    # Find the matching label / service for transit-time defaults.
    label = ShippingLabel.objects.filter(tracking_number=tracking_number).first()
    base_days = 7 if not label else label.service.max_transit_days
    eta_at = state.last_event_at + timedelta(days=max(1, base_days // 2))
    if state.current_status == 'out_for_delivery':
        eta_at = state.last_event_at + timedelta(hours=8)
    DeliveryEtaSnapshot.objects.filter(
        tracking_number=tracking_number, is_current=True,
    ).update(is_current=False)
    return DeliveryEtaSnapshot.objects.create(
        order_id=state.order_id, tracking_number=tracking_number,
        eta_at=eta_at,
        confidence=confidence_map.get(state.current_status, 0.5),
        rationale={'derived_from': state.current_status,
                   'last_event_at': state.last_event_at.isoformat()},
    )


# ═══════════════════════════════════════════════════════════════════
# CH9 — Address validation
# ═══════════════════════════════════════════════════════════════════

def _address_hash(addr: dict) -> str:
    raw = json.dumps(addr, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_address(*, address: dict) -> dict:
    """Cache-first validation. Production wires Google Address
    Validation or Loqate; dev does a structural check."""
    h = _address_hash(address)
    existing = AddressValidationResult.objects.filter(address_hash=h).first()
    if existing:
        return {
            'address_hash': h, 'valid': existing.valid,
            'standardised': existing.standardised,
            'deliverability_score': existing.deliverability_score,
            'suggestions': existing.suggestions, 'cached': True,
        }
    required = ['line1', 'city', 'country']
    missing = [f for f in required if not address.get(f)]
    valid = not missing
    score = 0.9 if valid else 0.2
    standardised = {
        'line1': (address.get('line1') or '').strip().title(),
        'line2': (address.get('line2') or '').strip().title(),
        'city': (address.get('city') or '').strip().title(),
        'postal_code': (address.get('postal_code') or '').strip().upper(),
        'state': (address.get('state') or '').strip().upper(),
        'country': (address.get('country') or '').strip().upper(),
    }
    suggestions = [{'field': f, 'reason': 'MISSING'} for f in missing]
    obj = AddressValidationResult.objects.create(
        address_hash=h, raw_address=address,
        standardised=standardised,
        country=standardised['country'][:2],
        valid=valid, deliverability_score=score,
        suggestions=suggestions,
    )
    return {'address_hash': h, 'valid': obj.valid,
            'standardised': obj.standardised,
            'deliverability_score': obj.deliverability_score,
            'suggestions': obj.suggestions, 'cached': False}


# ═══════════════════════════════════════════════════════════════════
# CH10 — DG carrier filter
# ═══════════════════════════════════════════════════════════════════

def filter_dg_carriers(*, product_id: str, sku_id: str = '') -> list[str]:
    """Returns allowed carrier codes for this SKU based on its hazmat
    classification (delegates to apps.pricing_inventory)."""
    try:
        from apps.pricing_inventory.models import ProductHazmat
        decl = ProductHazmat.objects.filter(
            product_id=product_id, sku_id=sku_id,
        ).select_related('hazmat_class').first()
        if not decl:
            return [c.code for c in Carrier.objects.filter(status='active')]
        if decl.hazmat_class.level == 'prohibited':
            return []
        allowed = decl.hazmat_class.allowed_carriers or []
        return list(
            Carrier.objects.filter(
                status='active', code__in=allowed,
            ).values_list('code', flat=True)
        )
    except Exception:
        return [c.code for c in Carrier.objects.filter(status='active')]


# ═══════════════════════════════════════════════════════════════════
# CH12 — COD
# ═══════════════════════════════════════════════════════════════════

def issue_cod(*, label: ShippingLabel, amount: Decimal,
               currency: str = 'AOA',
               collection_fee_pct: Decimal = Decimal('2.5')) -> CodTransaction:
    fee = (amount * collection_fee_pct / Decimal(100)).quantize(Decimal('0.01'))
    return CodTransaction.objects.create(
        order_id=label.order_id, label=label, amount=amount,
        currency=currency, collection_fee=fee,
    )


def mark_cod_collected(cod: CodTransaction) -> bool:
    if cod.status != 'pending':
        return False
    cod.status = 'collected'
    cod.collected_at = timezone.now()
    cod.save(update_fields=['status', 'collected_at'])
    LogisticsEvent.log(kind='cod.collected', order_id=cod.order_id,
                        payload={'amount': str(cod.amount)})
    return True


@transaction.atomic
def remit_cod_batch(*, carrier: Carrier, seller,
                      transactions: list[CodTransaction]) -> 'CodRemittance':
    from .models import CodRemittance
    if not transactions:
        raise ValueError('NO_TRANSACTIONS')
    total = sum(t.amount - t.collection_fee for t in transactions)
    batch_ref = 'COD-' + secrets.token_hex(8).upper()
    rem = CodRemittance.objects.create(
        carrier=carrier, seller=seller, batch_reference=batch_ref,
        total_amount=total, currency=transactions[0].currency,
        transaction_count=len(transactions), status='confirmed',
    )
    rem.transactions.set(transactions)
    for t in transactions:
        t.status = 'remitted'
        t.remitted_at = timezone.now()
        t.save(update_fields=['status', 'remitted_at'])
    LogisticsEvent.log(
        kind='cod.remittance_batch', seller=seller,
        payload={'batch': batch_ref, 'total': str(total),
                 'count': len(transactions)},
    )
    return rem


# ═══════════════════════════════════════════════════════════════════
# CH13 — Return labels
# ═══════════════════════════════════════════════════════════════════

def generate_return_label(*, order_id: str, buyer,
                            carrier: Carrier, service: CarrierService,
                            return_address: dict,
                            funded_by: str = 'buyer',
                            cost: Decimal = Decimal('0')) -> ReturnShipmentLabel:
    adapter = get_carrier_adapter(carrier.code)
    response = adapter.create_label(
        service_code=service.code,
        from_addr={}, to_addr=return_address,
        weight_kg=Decimal('1'), dimensions={},
        declared_value=cost or Decimal('100'),
    )
    return ReturnShipmentLabel.objects.create(
        order_id=order_id[:64], buyer=buyer, carrier=carrier,
        service=service, tracking_number=response.tracking_number,
        file_key=response.file_key, return_address=return_address,
        funded_by=funded_by, cost=cost, currency=service.currency,
    )


# ═══════════════════════════════════════════════════════════════════
# CH14 — Reverse logistics
# ═══════════════════════════════════════════════════════════════════

def record_return_inspection(*, order_id: str,
                                return_label: ReturnShipmentLabel = None,
                                decision: str = 'accept_full_refund',
                                grade: str = 'A',
                                disposition: str = 'restock',
                                inspector_notes: str = '') -> ReverseLogisticsRecord:
    obj = ReverseLogisticsRecord.objects.create(
        order_id=order_id[:64], return_label=return_label,
        received_at=timezone.now(),
        inspection_decision=decision, grade=grade,
        disposition=disposition, inspector_notes=inspector_notes,
    )
    if return_label and return_label.status != 'received':
        return_label.status = 'received'
        return_label.save(update_fields=['status'])
    LogisticsEvent.log(
        kind='return.inspected', order_id=order_id,
        payload={'decision': decision, 'grade': grade,
                 'disposition': disposition},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH16 — Wave planning
# ═══════════════════════════════════════════════════════════════════

def plan_fulfilment_wave(*, warehouse_code: str, order_ids: list[str],
                          sla_class: str = 'standard',
                          planned_for=None) -> FulfilmentWave:
    wave_number = f'W-{warehouse_code}-{secrets.token_hex(4).upper()}'
    return FulfilmentWave.objects.create(
        warehouse_code=warehouse_code[:20],
        wave_number=wave_number,
        planned_for=planned_for or timezone.now() + timedelta(hours=1),
        order_ids=order_ids,
        sla_class=sla_class,
    )


def advance_wave(wave: FulfilmentWave, *, to_status: str) -> bool:
    valid_next = {
        'planned':   ('released', 'cancelled'),
        'released':  ('picking', 'cancelled'),
        'picking':   ('packing', 'cancelled'),
        'packing':   ('dispatched', 'cancelled'),
        'dispatched':(),
        'cancelled': (),
    }
    if to_status not in valid_next.get(wave.status, ()):
        return False
    wave.status = to_status
    now = timezone.now()
    if to_status == 'picking':
        wave.pick_started_at = now
    elif to_status == 'packing':
        wave.pack_started_at = now
    elif to_status == 'dispatched':
        wave.dispatched_at = now
    wave.save()
    return True


# ═══════════════════════════════════════════════════════════════════
# CH17 — Stock transfer
# ═══════════════════════════════════════════════════════════════════

def propose_stock_transfer(*, from_warehouse: str, to_warehouse: str,
                             product_id: str, sku_id: str = '',
                             quantity: int = 0,
                             rationale: str = '') -> StockTransferOrder:
    return StockTransferOrder.objects.create(
        from_warehouse=from_warehouse[:20],
        to_warehouse=to_warehouse[:20],
        product_id=product_id[:64], sku_id=sku_id[:64],
        quantity=quantity, rationale=rationale[:255],
        status='proposed',
    )


def approve_stock_transfer(transfer: StockTransferOrder, *, approver) -> bool:
    if transfer.status != 'proposed':
        return False
    transfer.status = 'approved'
    transfer.approved_by = approver
    transfer.approved_at = timezone.now()
    transfer.save(update_fields=['status', 'approved_by', 'approved_at'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH18 — SLA snapshot
# ═══════════════════════════════════════════════════════════════════

def compute_carrier_sla_snapshot(*, snapshot_date=None) -> int:
    """Walk yesterday's deliveries to compute on-time pct per
    (carrier, service, destination). Returns rows written."""
    if snapshot_date is None:
        snapshot_date = timezone.now().date() - timedelta(days=1)
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)
    delivered = TrackingStatusUnified.objects.filter(
        delivered_at__gte=start, delivered_at__lt=end,
    ).select_related('carrier')
    rows = {}
    for d in delivered:
        # Find the label to recover service + dest country.
        lbl = ShippingLabel.objects.filter(tracking_number=d.tracking_number).first()
        if not lbl:
            continue
        dest = (lbl.to_address or {}).get('country', '')
        key = (lbl.carrier_id, lbl.service_id, dest)
        agg = rows.setdefault(key, {'count': 0, 'on_time': 0, 'late': 0,
                                     'transit_days': []})
        agg['count'] += 1
        promised = lbl.created_at + timedelta(days=lbl.service.max_transit_days)
        if d.delivered_at <= promised:
            agg['on_time'] += 1
        else:
            agg['late'] += 1
        agg['transit_days'].append(
            (d.delivered_at - lbl.created_at).days,
        )
    n = 0
    for (carrier_id, service_id, dest), agg in rows.items():
        on_time_pct = (agg['on_time'] / agg['count'] * 100) if agg['count'] else 0
        avg = sum(agg['transit_days']) / agg['count'] if agg['count'] else 0
        CarrierSlaSnapshot.objects.update_or_create(
            snapshot_date=snapshot_date,
            carrier_id=carrier_id, service_id=service_id,
            destination_country=dest[:2],
            defaults={
                'shipments_count': agg['count'],
                'on_time_count': agg['on_time'],
                'late_count': agg['late'],
                'avg_transit_days': avg,
                'on_time_pct': on_time_pct,
            },
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH18 — Failed delivery
# ═══════════════════════════════════════════════════════════════════

def record_failed_delivery(*, tracking_number: str, order_id: str,
                              reason: str, attempt: int = 1,
                              notes: str = '',
                              resolution: str = '') -> FailedDelivery:
    next_at = timezone.now() + timedelta(days=1)
    return FailedDelivery.objects.create(
        tracking_number=tracking_number[:80], order_id=order_id[:64],
        reason=reason, attempt_number=attempt, notes=notes[:5000],
        next_attempt_at=next_at, resolution=resolution,
    )


# ═══════════════════════════════════════════════════════════════════
# CH19 — Customs exception
# ═══════════════════════════════════════════════════════════════════

def record_customs_exception(*, tracking_number: str,
                                kind: str, description: str = '',
                                declaration=None,
                                requires_buyer_action: bool = False) -> CustomsException:
    return CustomsException.objects.create(
        tracking_number=tracking_number[:80], kind=kind,
        description=description[:5000], declaration=declaration,
        requires_buyer_action=requires_buyer_action,
    )


# ═══════════════════════════════════════════════════════════════════
# CH20 — Fulfilment exception
# ═══════════════════════════════════════════════════════════════════

def record_fulfilment_exception(*, order_id: str, kind: str,
                                   tracking_number: str = '',
                                   severity: int = 5,
                                   description: str = '',
                                   resolution: str = '') -> FulfilmentException:
    return FulfilmentException.objects.create(
        order_id=order_id[:64], tracking_number=tracking_number[:80],
        kind=kind, severity=severity, description=description[:5000],
        resolution=resolution,
    )


# ═══════════════════════════════════════════════════════════════════
# CH21 — Pickup point
# ═══════════════════════════════════════════════════════════════════

def assign_pickup_point(*, order_id: str, buyer,
                          tracking_number: str,
                          point_code: str,
                          hold_days: int = 7) -> PickupPointDelivery:
    point = PickupPoint.objects.get(code=point_code)
    code = secrets.token_urlsafe(6)[:8].upper()
    return PickupPointDelivery.objects.create(
        pickup_point=point, order_id=order_id[:64],
        tracking_number=tracking_number[:80], buyer=buyer,
        pickup_code=code,
        deadline_at=timezone.now() + timedelta(days=hold_days),
    )


def confirm_pickup(*, delivery: PickupPointDelivery) -> bool:
    if delivery.status not in ('in_transit', 'ready'):
        return False
    delivery.status = 'picked_up'
    delivery.picked_up_at = timezone.now()
    delivery.save(update_fields=['status', 'picked_up_at'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH22 — Choice local fulfilment
# ═══════════════════════════════════════════════════════════════════

def record_choice_local(*, order_id: str, warehouse_code: str,
                         domestic_carrier: Carrier,
                         promise_window_hours: int = 72) -> ChoiceLocalFulfilment:
    return ChoiceLocalFulfilment.objects.create(
        order_id=order_id[:64], warehouse_code=warehouse_code[:20],
        domestic_carrier=domestic_carrier,
        promise_window_hours=promise_window_hours,
    )


def mark_choice_dispatched(record: ChoiceLocalFulfilment,
                             *, pick_to_dispatch_minutes: int) -> None:
    record.actual_pick_to_dispatch_minutes = pick_to_dispatch_minutes
    record.sla_met = pick_to_dispatch_minutes <= record.pick_to_dispatch_target_minutes
    record.save(update_fields=['actual_pick_to_dispatch_minutes', 'sla_met'])


# ═══════════════════════════════════════════════════════════════════
# CH23 — Compliance check
# ═══════════════════════════════════════════════════════════════════

def check_compliance(*, sender_country: str, recipient_country: str,
                       declared_value_usd: Decimal,
                       items: list[dict] = None) -> dict:
    """Returns {ok, violations: [{rule_id, name, enforcement, ...}],
    required_docs: [...]}."""
    qs = ComplianceRule.objects.filter(
        recipient_country=recipient_country.upper(),
        is_active=True,
    ).filter(
        django_models.Q(sender_country=sender_country.upper()) |
        django_models.Q(sender_country='')
    )
    violations = []
    required_docs = []
    for rule in qs:
        cfg = rule.config or {}
        if rule.rule_kind == 'value_threshold':
            max_val = Decimal(str(cfg.get('max_value_usd', 0)))
            if max_val and declared_value_usd > max_val:
                violations.append({'rule_id': rule.pk, 'name': rule.name,
                                    'enforcement': rule.enforcement,
                                    'limit': str(max_val)})
        elif rule.rule_kind == 'docs_required':
            required_docs.extend(cfg.get('docs', []))
        elif rule.rule_kind == 'eori_required':
            required_docs.append('EORI number')
        elif rule.rule_kind == 'ioss_required':
            required_docs.append('IOSS number')
        elif rule.rule_kind == 'vat_registration':
            required_docs.append('VAT registration')
        elif rule.rule_kind == 'category_block':
            blocked = cfg.get('categories') or []
            if items:
                for it in items:
                    if it.get('category_id') in blocked:
                        violations.append({'rule_id': rule.pk,
                                            'name': rule.name,
                                            'enforcement': rule.enforcement,
                                            'category_id': it['category_id']})
    blocking = any(v.get('enforcement') == 'block' for v in violations)
    return {'ok': not blocking, 'violations': violations,
            'required_docs': list({d for d in required_docs})}


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_logistics_kpis(snapshot_date=None) -> LogisticsKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)
    created = ShippingLabel.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    delivered_qs = TrackingStatusUnified.objects.filter(
        delivered_at__gte=start, delivered_at__lt=end,
    )
    delivered = delivered_qs.count()
    transit_days = [
        (d.delivered_at - ShippingLabel.objects.get(tracking_number=d.tracking_number).created_at).days
        for d in delivered_qs
        if ShippingLabel.objects.filter(tracking_number=d.tracking_number).exists()
    ]
    avg_transit = sum(transit_days) / len(transit_days) if transit_days else 0
    on_time = sum(1 for td in transit_days if td <= 10)
    on_time_pct = (on_time / len(transit_days) * 100) if transit_days else 0
    failed = FailedDelivery.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end,
    ).count()
    customs_held = CustomsException.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    claims = InsuranceClaim.objects.filter(
        filed_at__gte=start, filed_at__lt=end,
    ).count()
    cod_collected = (
        CodTransaction.objects.filter(
            collected_at__gte=start, collected_at__lt=end,
        ).aggregate(s=django_models.Sum('amount'))['s'] or Decimal('0')
    )
    cod_pending = CodTransaction.objects.filter(status='pending').count()
    returns = ReverseLogisticsRecord.objects.filter(
        received_at__gte=start, received_at__lt=end,
    ).count()
    pickup_deliveries = PickupPointDelivery.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    pickup_pct = (pickup_deliveries / created * 100) if created else 0
    excp = FulfilmentException.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    by_carrier = dict(
        ShippingLabel.objects.filter(created_at__gte=start, created_at__lt=end)
        .values_list('carrier__code').annotate(c=django_models.Count('id'))
    )
    by_dest = {}
    for lbl in ShippingLabel.objects.filter(created_at__gte=start, created_at__lt=end):
        c = (lbl.to_address or {}).get('country', '')
        by_dest[c] = by_dest.get(c, 0) + 1

    obj, _ = LogisticsKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'shipments_created': created,
            'shipments_delivered': delivered,
            'avg_transit_days': avg_transit,
            'on_time_pct': on_time_pct,
            'delivery_success_pct': (delivered / created * 100) if created else 0,
            'failed_delivery_count': failed,
            'customs_held_count': customs_held,
            'insurance_claim_count': claims,
            'cod_collected_total': cod_collected,
            'cod_pending_count': cod_pending,
            'return_count': returns,
            'pickup_point_usage_pct': pickup_pct,
            'fulfilment_exception_count': excp,
            'by_carrier': {k or '': v for k, v in by_carrier.items()},
            'by_destination': by_dest,
        },
    )
    return obj
