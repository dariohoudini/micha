"""
Logistics & Fulfilment REST surface — thin views over services.py.
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .carriers.registry import get_carrier_adapter
from .models import (
    Carrier, CarrierService, ChoiceLocalFulfilment, CodRemittance,
    CodTransaction, ComplianceRule, CustomsDeclaration,
    CustomsException, DeliveryEtaSnapshot, FailedDelivery,
    FulfilmentException, FulfilmentWave, InboundShipmentItem,
    InsuranceClaim, LogisticsEvent, LogisticsKpiSnapshot,
    PackJob, ParcelInsurancePolicy, PickList, PickupPoint,
    PickupPointDelivery, ReturnShipmentLabel,
    ReverseLogisticsRecord, ShippingLabel, StockTransferOrder,
    TrackingNormalisedEvent, TrackingStatusUnified,
    WarehouseInboundShipment,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH1 — Carriers ────────────────────────────────────────────

class CarrierListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(list(Carrier.objects.filter(status='active').values(
            'code', 'name', 'tier', 'country_scope', 'supports_ddp',
            'supports_cod', 'supports_dangerous_goods',
            'on_time_rate', 'health_score', 'average_transit_days',
        )))


# ─── CH2 — Carrier selection / quote ──────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def carrier_select(request):
    """POST /carriers/select  body: {from_country, to_country,
    weight_kg, declared_value, needs_ddp, needs_cod, needs_dangerous,
    sla_class}."""
    return Response(services.select_best_service(
        from_country=request.data.get('from_country', ''),
        to_country=request.data.get('to_country', ''),
        weight_kg=Decimal(str(request.data.get('weight_kg', 1))),
        declared_value=Decimal(str(request.data.get('declared_value', 0))),
        needs_ddp=bool(request.data.get('needs_ddp', False)),
        needs_cod=bool(request.data.get('needs_cod', False)),
        needs_dangerous=bool(request.data.get('needs_dangerous', False)),
        sla_class=request.data.get('sla_class', 'standard'),
    ))


# ─── CH3 — Label generation ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def label_generate(request):
    label = services.generate_label(
        order_id=request.data.get('order_id', ''),
        seller=request.user,
        carrier_code=request.data.get('carrier_code', ''),
        service_id=int(request.data.get('service_id', 0)),
        from_addr=request.data.get('from_addr') or {},
        to_addr=request.data.get('to_addr') or {},
        weight_kg=Decimal(str(request.data.get('weight_kg', 1))),
        dimensions=request.data.get('dimensions') or {},
        declared_value=Decimal(str(request.data.get('declared_value', 0))),
        currency=request.data.get('currency', 'AOA'),
        incoterm=request.data.get('incoterm', 'DAP'),
    )
    return Response({
        'label_id': str(label.id),
        'tracking_number': label.tracking_number,
        'file_key': label.file_key,
        'status': label.status,
    }, status=201)


class MyLabelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = ShippingLabel.objects.filter(seller=request.user).values(
            'id', 'order_id', 'tracking_number', 'carrier_id',
            'service_id', 'declared_value', 'currency',
            'status', 'created_at',
        )[:200]
        return Response(list(rows))


# ─── CH4 — Customs + HS code ──────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def hs_classify(request):
    return Response(services.classify_hs_code(
        product_id=request.data.get('product_id', ''),
        title=request.data.get('title', ''),
        category_id=request.data.get('category_id', ''),
    ))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def customs_generate(request):
    label = get_object_or_404(ShippingLabel,
                              pk=request.data.get('label_id'),
                              seller=request.user)
    decl = services.generate_customs_declaration(
        label=label, items=request.data.get('items') or [],
        incoterm=request.data.get('incoterm', 'DAP'),
        eori_number=request.data.get('eori_number', ''),
    )
    return Response({
        'declaration_id': str(decl.id),
        'duty_estimate_amount': str(decl.duty_estimate_amount),
        'tax_estimate_amount': str(decl.tax_estimate_amount),
    }, status=201)


# ─── CH5 — Duty estimate ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def duty_compute(request):
    return Response(services.compute_duty_estimate(
        items=request.data.get('items') or [],
        destination_country=request.data.get('destination_country', ''),
        incoterm=request.data.get('incoterm', 'DAP'),
        currency=request.data.get('currency', 'USD'),
    ))


# ─── CH6 — Insurance ───────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def insurance_issue(request):
    label = get_object_or_404(ShippingLabel,
                              pk=request.data.get('label_id'),
                              seller=request.user)
    policy = services.issue_insurance_policy(
        label=label,
        declared_value=Decimal(str(request.data.get('declared_value', label.declared_value))),
        coverage=request.data.get('coverage', 'loss_damage'),
    )
    return Response({
        'policy_id': str(policy.id),
        'premium_amount': str(policy.premium_amount),
        'currency': policy.currency,
        'valid_until': policy.valid_until.isoformat(),
    }, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def insurance_claim(request):
    policy = get_object_or_404(ParcelInsurancePolicy,
                                pk=request.data.get('policy_id'))
    try:
        claim = services.file_insurance_claim(
            policy=policy, claimant=request.user,
            reason=request.data.get('reason', 'lost'),
            claim_amount=Decimal(str(request.data.get('claim_amount', 0))),
            description=request.data.get('description', ''),
            evidence_keys=request.data.get('evidence_keys') or [],
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'claim_id': str(claim.id),
                     'status': claim.status}, status=201)


# ─── CH7 — Tracking webhook + status ──────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def tracking_webhook(request, carrier_code):
    """POST /tracking/<carrier_code>/webhook — parse + ingest."""
    carrier = get_object_or_404(Carrier, code=carrier_code)
    adapter = get_carrier_adapter(carrier_code)
    body = request.body
    updates = adapter.parse_webhook(
        headers={k: v for k, v in request.META.items() if k.startswith('HTTP_')},
        body=body, body_text=body.decode('utf-8', errors='replace'),
    )
    ingested = 0
    for u in updates:
        # The dev stub returns occurred_at as a string; coerce.
        from datetime import datetime
        try:
            occurred = datetime.fromisoformat(u.occurred_at) if u.occurred_at else timezone.now()
            if occurred.tzinfo is None:
                occurred = timezone.make_aware(occurred)
        except Exception:
            occurred = timezone.now()
        ok = services.ingest_tracking_event(
            tracking_number=request.data.get('tracking_number') or '',
            carrier=carrier,
            raw_status=u.raw_status,
            normalised_status=u.normalised_status,
            occurred_at=occurred,
            carrier_event_id=u.carrier_event_id,
            location=u.location,
            raw_payload=request.data if isinstance(request.data, dict) else {},
            classifier_confidence=u.confidence,
        )
        if ok:
            ingested += 1
    return Response({'ingested': ingested})


class TrackingStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, tracking_number):
        state = get_object_or_404(TrackingStatusUnified, tracking_number=tracking_number)
        events = TrackingNormalisedEvent.objects.filter(
            tracking_number=tracking_number,
        ).order_by('-occurred_at').values(
            'normalised_status', 'location', 'occurred_at',
        )[:50]
        return Response({
            'tracking_number': state.tracking_number,
            'current_status': state.current_status,
            'last_event_at': state.last_event_at.isoformat(),
            'last_known_location': state.last_known_location,
            'delivered_at': state.delivered_at and state.delivered_at.isoformat(),
            'history': list(events),
        })


# ─── CH8 — ETA ─────────────────────────────────────────────────

class TrackingEtaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, tracking_number):
        snap = (
            DeliveryEtaSnapshot.objects.filter(
                tracking_number=tracking_number, is_current=True,
            ).order_by('-computed_at').first()
        )
        if not snap:
            snap = services.refresh_eta_snapshot(tracking_number=tracking_number)
        if not snap:
            return Response({'detail': 'no eta'}, status=404)
        return Response({
            'eta_at': snap.eta_at.isoformat(),
            'confidence': snap.confidence,
            'rationale': snap.rationale,
            'computed_at': snap.computed_at.isoformat(),
        })


# ─── CH9 — Address validation ─────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def address_validate(request):
    return Response(services.validate_address(
        address=request.data.get('address') or {},
    ))


# ─── CH10 — DG carrier filter ─────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def dg_carrier_filter(request):
    codes = services.filter_dg_carriers(
        product_id=request.data.get('product_id', ''),
        sku_id=request.data.get('sku_id', ''),
    )
    return Response({'allowed_carrier_codes': codes})


# ─── CH12 — COD ────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cod_issue(request):
    label = get_object_or_404(ShippingLabel,
                              pk=request.data.get('label_id'),
                              seller=request.user)
    cod = services.issue_cod(
        label=label,
        amount=Decimal(str(request.data.get('amount', 0))),
        currency=request.data.get('currency', 'AOA'),
    )
    return Response({'cod_id': str(cod.id),
                     'collection_fee': str(cod.collection_fee)},
                    status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def cod_collected(request):
    cod = get_object_or_404(CodTransaction, pk=request.data.get('cod_id'))
    ok = services.mark_cod_collected(cod)
    return Response({'ok': ok}, status=200 if ok else 409)


@api_view(['POST'])
@permission_classes([IsAdmin])
def cod_remit(request):
    carrier = get_object_or_404(Carrier, code=request.data.get('carrier_code'))
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    txn_ids = request.data.get('transaction_ids') or []
    transactions = list(CodTransaction.objects.filter(
        pk__in=txn_ids, status='collected',
    ))
    if not transactions:
        return Response({'detail': 'no eligible transactions'}, status=422)
    rem = services.remit_cod_batch(
        carrier=carrier, seller=seller, transactions=transactions,
    )
    return Response({'remittance_id': str(rem.id),
                     'batch_reference': rem.batch_reference,
                     'total_amount': str(rem.total_amount)},
                    status=201)


# ─── CH13 — Return labels ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def return_label_generate(request):
    carrier = get_object_or_404(Carrier, code=request.data.get('carrier_code'))
    service = get_object_or_404(CarrierService,
                                pk=request.data.get('service_id'),
                                carrier=carrier)
    obj = services.generate_return_label(
        order_id=request.data.get('order_id', ''),
        buyer=request.user,
        carrier=carrier, service=service,
        return_address=request.data.get('return_address') or {},
        funded_by=request.data.get('funded_by', 'buyer'),
        cost=Decimal(str(request.data.get('cost', 0))),
    )
    return Response({
        'return_label_id': str(obj.id),
        'tracking_number': obj.tracking_number,
        'file_key': obj.file_key,
    }, status=201)


# ─── CH14 — Reverse logistics ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reverse_inspect(request):
    return_label = None
    if request.data.get('return_label_id'):
        return_label = ReturnShipmentLabel.objects.filter(
            pk=request.data['return_label_id']).first()
    obj = services.record_return_inspection(
        order_id=request.data.get('order_id', ''),
        return_label=return_label,
        decision=request.data.get('decision', 'accept_full_refund'),
        grade=request.data.get('grade', 'A'),
        disposition=request.data.get('disposition', 'restock'),
        inspector_notes=request.data.get('inspector_notes', ''),
    )
    return Response({'record_id': str(obj.id)}, status=201)


# ─── CH15 — Inbound shipment ──────────────────────────────────

class InboundShipmentView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WarehouseInboundShipment.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        carrier = None
        if request.data.get('carrier_code'):
            carrier = Carrier.objects.filter(code=request.data['carrier_code']).first()
        from datetime import date
        try:
            arrival = date.fromisoformat(request.data.get('expected_arrival_date', ''))
        except Exception:
            arrival = timezone.now().date()
        ship = WarehouseInboundShipment.objects.create(
            seller=request.user,
            warehouse_code=request.data.get('warehouse_code', '')[:20],
            asn_reference=request.data.get('asn_reference', '')[:64] or
                          ('ASN-' + str(timezone.now().timestamp())),
            expected_arrival_date=arrival,
            carrier=carrier,
            tracking_number=request.data.get('tracking_number', '')[:80],
        )
        for it in (request.data.get('items') or []):
            InboundShipmentItem.objects.create(
                shipment=ship,
                product_id=it.get('product_id', '')[:64],
                sku_id=it.get('sku_id', '')[:64],
                expected_qty=int(it.get('expected_qty', 0)),
            )
        return Response({'shipment_id': str(ship.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def inbound_receive(request):
    """Record QC outcome on an inbound shipment."""
    ship = get_object_or_404(WarehouseInboundShipment,
                              pk=request.data.get('shipment_id'),
                              seller=request.user)
    items_payload = request.data.get('items') or []
    for it_in in items_payload:
        item = InboundShipmentItem.objects.filter(
            shipment=ship, product_id=it_in.get('product_id', ''),
            sku_id=it_in.get('sku_id', ''),
        ).first()
        if not item:
            continue
        item.received_qty = int(it_in.get('received_qty', 0))
        item.rejected_qty = int(it_in.get('rejected_qty', 0))
        item.discrepancy_reason = it_in.get('discrepancy_reason', '')[:120]
        item.save()
    ship.actual_arrival_at = timezone.now()
    # Determine final status.
    items = list(ship.items.all())
    if all(i.received_qty == i.expected_qty for i in items):
        ship.status = 'qc_passed'
    elif any(i.received_qty for i in items):
        ship.status = 'partial'
    else:
        ship.status = 'rejected'
    ship.save(update_fields=['actual_arrival_at', 'status'])
    return Response({'status': ship.status})


# ─── CH16 — Waves / picking / packing ─────────────────────────

class FulfilmentWaveView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FulfilmentWave.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values()[:100]))

    def create(self, request):
        wave = services.plan_fulfilment_wave(
            warehouse_code=request.data.get('warehouse_code', ''),
            order_ids=request.data.get('order_ids') or [],
            sla_class=request.data.get('sla_class', 'standard'),
        )
        return Response({'wave_id': str(wave.id),
                         'wave_number': wave.wave_number}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wave_advance(request):
    wave = get_object_or_404(FulfilmentWave, pk=request.data.get('wave_id'))
    ok = services.advance_wave(wave, to_status=request.data.get('to_status', ''))
    return Response({'ok': ok, 'status': wave.status})


# ─── CH17 — Stock transfer ────────────────────────────────────

class StockTransferView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return StockTransferOrder.objects.all().order_by('-created_at')

    def list(self, request):
        return Response(list(self.get_queryset().values()[:100]))

    def create(self, request):
        obj = services.propose_stock_transfer(
            from_warehouse=request.data.get('from_warehouse', ''),
            to_warehouse=request.data.get('to_warehouse', ''),
            product_id=request.data.get('product_id', ''),
            sku_id=request.data.get('sku_id', ''),
            quantity=int(request.data.get('quantity', 0)),
            rationale=request.data.get('rationale', ''),
        )
        return Response({'transfer_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def stock_transfer_approve(request):
    obj = get_object_or_404(StockTransferOrder,
                            pk=request.data.get('transfer_id'))
    ok = services.approve_stock_transfer(obj, approver=request.user)
    return Response({'ok': ok, 'status': obj.status})


# ─── CH18 — SLA + failed delivery ─────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def failed_delivery_record(request):
    obj = services.record_failed_delivery(
        tracking_number=request.data.get('tracking_number', ''),
        order_id=request.data.get('order_id', ''),
        reason=request.data.get('reason', 'other'),
        attempt=int(request.data.get('attempt', 1)),
        notes=request.data.get('notes', ''),
        resolution=request.data.get('resolution', ''),
    )
    return Response({'failed_delivery_id': obj.pk}, status=201)


# ─── CH19 — Customs exception ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def customs_exception_record(request):
    decl = None
    if request.data.get('declaration_id'):
        decl = CustomsDeclaration.objects.filter(pk=request.data['declaration_id']).first()
    obj = services.record_customs_exception(
        tracking_number=request.data.get('tracking_number', ''),
        kind=request.data.get('kind', 'held_for_inspection'),
        description=request.data.get('description', ''),
        declaration=decl,
        requires_buyer_action=bool(request.data.get('requires_buyer_action', False)),
    )
    return Response({'exception_id': obj.pk}, status=201)


# ─── CH20 — Fulfilment exception ──────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def fulfilment_exception_record(request):
    obj = services.record_fulfilment_exception(
        order_id=request.data.get('order_id', ''),
        kind=request.data.get('kind', 'damaged_in_transit'),
        tracking_number=request.data.get('tracking_number', ''),
        severity=int(request.data.get('severity', 5)),
        description=request.data.get('description', ''),
        resolution=request.data.get('resolution', ''),
    )
    return Response({'exception_id': obj.pk}, status=201)


# ─── CH21 — Pickup points + lockers ───────────────────────────

class PickupPointListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        country = request.query_params.get('country', '')
        qs = PickupPoint.objects.filter(is_active=True)
        if country:
            qs = qs.filter(country=country.upper())
        return Response(list(qs.values(
            'code', 'name', 'kind', 'country', 'city', 'capacity',
            'current_load', 'opening_hours',
        )[:100]))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pickup_assign(request):
    obj = services.assign_pickup_point(
        order_id=request.data.get('order_id', ''),
        buyer=request.user,
        tracking_number=request.data.get('tracking_number', ''),
        point_code=request.data.get('point_code', ''),
        hold_days=int(request.data.get('hold_days', 7)),
    )
    return Response({'delivery_id': obj.pk,
                     'pickup_code': obj.pickup_code,
                     'deadline_at': obj.deadline_at.isoformat()},
                    status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pickup_confirm(request):
    delivery = get_object_or_404(PickupPointDelivery,
                                  pk=request.data.get('delivery_id'),
                                  buyer=request.user)
    ok = services.confirm_pickup(delivery=delivery)
    return Response({'ok': ok})


# ─── CH22 — Choice local ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def choice_local_record(request):
    carrier = get_object_or_404(Carrier, code=request.data.get('domestic_carrier'))
    obj = services.record_choice_local(
        order_id=request.data.get('order_id', ''),
        warehouse_code=request.data.get('warehouse_code', ''),
        domestic_carrier=carrier,
        promise_window_hours=int(request.data.get('promise_window_hours', 72)),
    )
    return Response({'record_id': str(obj.id)}, status=201)


# ─── CH23 — Compliance check ──────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def compliance_check(request):
    return Response(services.check_compliance(
        sender_country=request.data.get('sender_country', ''),
        recipient_country=request.data.get('recipient_country', ''),
        declared_value_usd=Decimal(str(request.data.get('declared_value_usd', 0))),
        items=request.data.get('items') or [],
    ))


# ─── CH24 — KPI ───────────────────────────────────────────────

class LogisticsKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = LogisticsKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_logistics_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'shipments_created': snap.shipments_created,
            'shipments_delivered': snap.shipments_delivered,
            'avg_transit_days': snap.avg_transit_days,
            'on_time_pct': snap.on_time_pct,
            'delivery_success_pct': snap.delivery_success_pct,
            'failed_delivery_count': snap.failed_delivery_count,
            'customs_held_count': snap.customs_held_count,
            'insurance_claim_count': snap.insurance_claim_count,
            'cod_collected_total': str(snap.cod_collected_total),
            'cod_pending_count': snap.cod_pending_count,
            'return_count': snap.return_count,
            'pickup_point_usage_pct': snap.pickup_point_usage_pct,
            'fulfilment_exception_count': snap.fulfilment_exception_count,
            'by_carrier': snap.by_carrier,
            'by_destination': snap.by_destination,
        })

    def post(self, request):
        snap = services.snapshot_logistics_kpis()
        return Response({'date': str(snap.snapshot_date),
                         'shipments_created': snap.shipments_created})
