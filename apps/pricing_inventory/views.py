"""
Pricing & Inventory REST surface — thin views over services.py.
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
from .models import (
    BackorderConfig, BackorderRequest, DropshipMapping, DropshipOrder,
    DropshipSupplier, DynamicPricingConfig, HazmatClass,
    InventoryAuditEntry, InventoryAuditRun, InventoryWebhook,
    OversizeSurchargeRule, PreOrderConfig, PreOrderReservation,
    PriceCap, PriceFloor, PriceHistory, PriceRule,
    PricingInventoryEvent, PricingInventoryKpiSnapshot,
    ProductHazmat, RegionalPriceAdjustment, ReturnInventoryReceipt,
    StockAlert, VirtualBundleInventory, Warehouse, WarehouseStock,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH1 — Price resolve ───────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def price_resolve(request):
    """POST /price/resolve  body: {product_id, sku_id, country}."""
    user = request.user if request.user.is_authenticated else None
    result = services.resolve_price(
        product_id=request.data.get('product_id', '')[:64],
        sku_id=request.data.get('sku_id', '')[:64],
        country=request.data.get('country', '')[:2],
        user=user,
    )
    if result['final_price'] is not None:
        result['final_price'] = str(result['final_price'])
    return Response(result)


class PriceRuleListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return PriceRule.objects.all()
        return PriceRule.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'layer', 'product_id', 'sku_id', 'country',
            'price_amount', 'currency', 'discount_pct',
            'priority_score', 'valid_from', 'valid_until',
            'status', 'source', 'created_at',
        )[:200]))

    def create(self, request):
        obj = PriceRule.objects.create(
            layer=request.data.get('layer', 'seller_override'),
            seller=request.user,
            product_id=request.data.get('product_id', '')[:64],
            sku_id=request.data.get('sku_id', '')[:64],
            country=request.data.get('country', '')[:2],
            price_amount=Decimal(str(request.data.get('price_amount', 0))),
            currency=request.data.get('currency', 'AOA'),
            discount_pct=Decimal(str(request.data.get('discount_pct', 0))),
            priority_score=int(request.data.get('priority_score', 50)),
            valid_from=request.data.get('valid_from') or timezone.now(),
            valid_until=request.data.get('valid_until'),
            source=request.data.get('source', 'seller_console')[:40],
            metadata=request.data.get('metadata') or {},
            created_by=request.user,
        )
        services.record_price_change(
            product_id=obj.product_id, sku_id=obj.sku_id,
            country=obj.country, new_price=obj.price_amount,
            currency=obj.currency, source=obj.source,
            actor=request.user, rule=obj,
        )
        return Response({'rule_id': str(obj.id)}, status=201)


@api_view(['GET'])
@permission_classes([AllowAny])
def was_price(request):
    """GET /price/was-price?product_id=...&sku_id=...&country=..."""
    val = services.was_price_30d(
        product_id=request.query_params.get('product_id', ''),
        sku_id=request.query_params.get('sku_id', ''),
        country=request.query_params.get('country', ''),
    )
    return Response({'was_price_30d': str(val) if val else None})


# ─── CH2 — Dynamic pricing ────────────────────────────────────

class DynamicPricingConfigView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DynamicPricingConfig.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'product_id', 'sku_id', 'enabled',
            'min_price', 'max_price', 'cost_basis',
            'aggressiveness', 'last_applied_at',
        )))

    def create(self, request):
        obj = DynamicPricingConfig.objects.create(
            seller=request.user,
            product_id=request.data.get('product_id', '')[:64],
            sku_id=request.data.get('sku_id', '')[:64],
            enabled=bool(request.data.get('enabled', False)),
            min_price=Decimal(str(request.data.get('min_price', 0))),
            max_price=Decimal(str(request.data.get('max_price', 0))),
            cost_basis=Decimal(str(request.data.get('cost_basis', 0))),
            use_time_signal=bool(request.data.get('use_time_signal', True)),
            use_demand_signal=bool(request.data.get('use_demand_signal', True)),
            use_competitor_signal=bool(request.data.get('use_competitor_signal', True)),
            aggressiveness=int(request.data.get('aggressiveness', 5)),
        )
        return Response({'config_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_dynamic(request):
    cfg = get_object_or_404(DynamicPricingConfig,
                            pk=request.data.get('config_id'),
                            seller=request.user)
    return Response(services.evaluate_dynamic_pricing(cfg))


# ─── CH3/4 — Floor + cap check ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def floor_cap_check(request):
    cost = request.data.get('cost_basis')
    return Response(services.check_floor_cap(
        price=Decimal(str(request.data.get('price', 0))),
        currency=request.data.get('currency', 'AOA'),
        category_id=request.data.get('category_id', ''),
        country=request.data.get('country', ''),
        cost_basis=Decimal(str(cost)) if cost is not None else None,
    ))


# ─── CH6 — Competitor observations ─────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def competitor_record(request):
    obj = services.record_competitor_observation(
        product_id=request.data.get('product_id', ''),
        source=request.data.get('source', 'manual'),
        observed_price=request.data.get('observed_price', 0),
        currency=request.data.get('currency', 'AOA'),
        competitor_url=request.data.get('competitor_url', ''),
        competitor_seller=request.data.get('competitor_seller', ''),
        in_stock=bool(request.data.get('in_stock', True)),
    )
    return Response({'observation_id': obj.pk}, status=201)


# ─── CH7.2 — Regional adjustment (admin) ──────────────────────

class RegionalAdjustmentView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return RegionalPriceAdjustment.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj = RegionalPriceAdjustment.objects.create(
            country=request.data.get('country', '').upper()[:2],
            category_id=request.data.get('category_id', '')[:64],
            product_id=request.data.get('product_id', '')[:64],
            multiplier=Decimal(str(request.data.get('multiplier', 1))),
            rationale=request.data.get('rationale', '')[:255],
            valid_from=request.data.get('valid_from') or timezone.now(),
            valid_until=request.data.get('valid_until'),
        )
        return Response({'id': obj.pk}, status=201)


# ─── CH9 — Safety stock + reorder ──────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def compute_safety(request):
    daily = float(request.data.get('daily_avg', 0))
    lead = int(request.data.get('lead_time_days', 7))
    ss = services.compute_safety_stock(daily_avg=daily, lead_time_days=lead)
    rp = services.compute_reorder_point(
        daily_avg=daily, lead_time_days=lead, safety_stock=ss,
    )
    return Response({'safety_stock': ss, 'reorder_point': rp})


# ─── CH15 — Warehouse + routing ────────────────────────────────

class WarehouseView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Warehouse.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj = Warehouse.objects.create(
            seller=request.user,
            code=request.data.get('code', '')[:20],
            name=request.data.get('name', '')[:160],
            country=request.data.get('country', '').upper()[:2],
            city=request.data.get('city', '')[:80],
            coords=request.data.get('coords') or {},
            capacity_units=int(request.data.get('capacity_units', 10000)),
        )
        return Response({'warehouse_id': obj.pk, 'code': obj.code}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def warehouse_route(request):
    """POST /warehouses/route  body:
    {product_id, sku_id, quantity, destination_country, destination_coords?}."""
    return Response(services.route_to_warehouse(
        product_id=request.data.get('product_id', ''),
        sku_id=request.data.get('sku_id', ''),
        quantity=int(request.data.get('quantity', 1)),
        destination_country=request.data.get('destination_country', ''),
        destination_coords=request.data.get('destination_coords') or None,
    ))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def warehouse_reserve(request):
    ok = services.reserve_warehouse_stock(
        warehouse_code=request.data.get('warehouse_code', ''),
        product_id=request.data.get('product_id', ''),
        sku_id=request.data.get('sku_id', ''),
        quantity=int(request.data.get('quantity', 1)),
    )
    return Response({'ok': ok}, status=200 if ok else 409)


# ─── CH16 — Inventory webhook ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def inventory_webhook_ingest(request):
    """POST /inventory/webhook  body: {external_event_id, product_id,
    sku_id, new_on_hand, signature, payload}."""
    obj, created = InventoryWebhook.objects.get_or_create(
        seller=request.user,
        external_event_id=request.data.get('external_event_id', '')[:120],
        defaults={
            'product_id': request.data.get('product_id', '')[:64],
            'sku_id': request.data.get('sku_id', '')[:64],
            'new_on_hand': int(request.data.get('new_on_hand', 0)),
            'payload': request.data.get('payload') or {},
            'signature_valid': True,
        },
    )
    if not created:
        return Response({'ok': True, 'duplicate': True})
    services.apply_inventory_webhook(obj)
    return Response({'ok': True, 'webhook_id': obj.pk}, status=201)


# ─── CH17 — Stock alerts ──────────────────────────────────────

class MyStockAlertsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = StockAlert.objects.filter(seller=request.user).values(
            'product_id', 'sku_id', 'tier', 'days_of_cover',
            'on_hand', 'auto_action', 'transitioned_at',
        )[:200]
        return Response(list(rows))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reevaluate_alerts(request):
    n = services.evaluate_stock_alerts(seller=request.user)
    return Response({'transitions': n})


# ─── CH12 — Pre-order ─────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def preorder_reserve_view(request):
    cfg = get_object_or_404(PreOrderConfig, pk=request.data.get('config_id'))
    try:
        res = services.reserve_preorder(
            config=cfg, user=request.user,
            quantity=int(request.data.get('quantity', 1)),
            full_amount=Decimal(str(request.data.get('full_amount', 0))),
            currency=request.data.get('currency', 'AOA'),
            psp_intent_id=request.data.get('psp_intent_id', ''),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'reservation_id': str(res.id),
                     'deposit_amount': str(res.deposit_amount)},
                    status=201)


class PreOrderConfigView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PreOrderConfig.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj = PreOrderConfig.objects.create(
            seller=request.user,
            product_id=request.data.get('product_id', '')[:64],
            sku_id=request.data.get('sku_id', '')[:64],
            enabled=bool(request.data.get('enabled', True)),
            deposit_pct=int(request.data.get('deposit_pct', 0)),
            max_units=int(request.data.get('max_units', 0)),
            expected_ship_at=request.data.get('expected_ship_at') or timezone.now(),
        )
        return Response({'config_id': obj.pk}, status=201)


# ─── CH13 — Backorder ─────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def backorder_queue_view(request):
    cfg = get_object_or_404(BackorderConfig, pk=request.data.get('config_id'))
    try:
        req = services.queue_backorder(
            config=cfg, user=request.user,
            quantity=int(request.data.get('quantity', 1)),
            order_id=request.data.get('order_id', ''),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'request_id': str(req.id),
                     'queue_position': req.queue_position,
                     'deadline_at': req.deadline_at.isoformat()},
                    status=201)


# ─── CH14 — Dropship ──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dropship_route(request):
    obj = services.route_to_dropship(
        seller_product_id=request.data.get('seller_product_id', '')[:64],
        seller_sku_id=request.data.get('seller_sku_id', '')[:64],
        order_id=request.data.get('order_id', '')[:64],
        quantity=int(request.data.get('quantity', 1)),
    )
    if not obj:
        return Response({'code': 'NO_MAPPING'}, status=404)
    return Response({'dropship_order_id': str(obj.id),
                     'sla_deadline_at': obj.sla_deadline_at.isoformat(),
                     'supplier_id': obj.supplier_id}, status=201)


# ─── CH18 — Return ────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def return_receive(request):
    wh = None
    if request.data.get('warehouse_id'):
        wh = Warehouse.objects.filter(pk=request.data['warehouse_id']).first()
    receipt = services.receive_return(
        seller=request.user,
        order_id=request.data.get('order_id', '')[:64],
        product_id=request.data.get('product_id', '')[:64],
        sku_id=request.data.get('sku_id', '')[:64],
        quantity=int(request.data.get('quantity', 1)),
        grade=request.data.get('grade', 'A'),
        disposition=request.data.get('disposition', 'restock'),
        warehouse=wh,
        return_reason=request.data.get('return_reason', ''),
    )
    return Response({'receipt_id': str(receipt.id)}, status=201)


# ─── CH19 — Audit ─────────────────────────────────────────────

class AuditRunView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InventoryAuditRun.objects.filter(seller=self.request.user)

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        wh = get_object_or_404(Warehouse, pk=request.data.get('warehouse_id'))
        obj = InventoryAuditRun.objects.create(
            seller=request.user, warehouse=wh,
            scheduled_for=request.data.get('scheduled_for') or timezone.now().date(),
        )
        return Response({'audit_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def audit_record_entry(request):
    audit = get_object_or_404(InventoryAuditRun,
                              pk=request.data.get('audit_id'),
                              seller=request.user)
    sys = int(request.data.get('system_on_hand', 0))
    phys = int(request.data.get('physical_count', 0))
    InventoryAuditEntry.objects.create(
        run=audit, product_id=request.data.get('product_id', '')[:64],
        sku_id=request.data.get('sku_id', '')[:64],
        system_on_hand=sys, physical_count=phys, delta=phys - sys,
    )
    return Response({'ok': True}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def audit_finalise(request):
    audit = get_object_or_404(InventoryAuditRun,
                              pk=request.data.get('audit_id'),
                              seller=request.user)
    return Response(services.finalise_audit_run(audit))


# ─── CH20 — Hazmat ────────────────────────────────────────────

class ProductHazmatView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProductHazmat.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        cls = get_object_or_404(HazmatClass, code=request.data.get('hazmat_class', ''))
        obj = ProductHazmat.objects.create(
            product_id=request.data.get('product_id', '')[:64],
            sku_id=request.data.get('sku_id', '')[:64],
            hazmat_class=cls,
            un_number=request.data.get('un_number', '')[:20],
            safety_data_sheet_key=request.data.get('safety_data_sheet_key', '')[:255],
            declared_by=request.user,
        )
        return Response({'id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def hazmat_check(request):
    return Response(services.check_hazmat_allowed(
        product_id=request.data.get('product_id', ''),
        sku_id=request.data.get('sku_id', ''),
        carrier=request.data.get('carrier', ''),
    ))


# ─── CH21 — Oversize surcharge ────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def oversize_surcharge(request):
    return Response(services.compute_oversize_surcharge(
        country=request.data.get('country', ''),
        carrier=request.data.get('carrier', ''),
        weight_kg=Decimal(str(request.data.get('weight_kg', 0))),
        length_cm=int(request.data.get('length_cm', 0)),
        width_cm=int(request.data.get('width_cm', 0)),
        height_cm=int(request.data.get('height_cm', 0)),
    ))


# ─── CH22 — Virtual bundle ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def virtual_bundle_recompute(request):
    n = services.recompute_virtual_bundle(
        bundle_id=request.data.get('bundle_id', ''),
        components=request.data.get('components') or [],
    )
    return Response({'available_bundles': n})


# ─── CH24 — KPI dashboard ─────────────────────────────────────

class PIKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = PricingInventoryKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_pi_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'price_change_count': snap.price_change_count,
            'price_floor_violations': snap.price_floor_violations,
            'price_cap_violations': snap.price_cap_violations,
            'avg_stock_accuracy': snap.avg_stock_accuracy,
            'stockout_skus': snap.stockout_skus,
            'critical_skus': snap.critical_skus,
            'preorder_units': snap.preorder_units,
            'backorder_units': snap.backorder_units,
            'dropship_orders': snap.dropship_orders,
            'by_warehouse': snap.by_warehouse,
        })

    def post(self, request):
        snap = services.snapshot_pi_kpis()
        return Response({'date': str(snap.snapshot_date)})


# ─── CH23 — Real-time seller inventory dashboard ──────────────

class SellerInventoryDashboardView(APIView):
    """GET /dashboard/me — aggregated view: stock by warehouse,
    alerts, pre/back order queues, audit accuracy."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Sum, Avg
        wh_rows = (
            WarehouseStock.objects.filter(warehouse__seller=request.user)
            .values('warehouse__code')
            .annotate(on_hand=Sum('on_hand'), reserved=Sum('reserved'))
        )
        alerts_by_tier = dict(
            StockAlert.objects.filter(seller=request.user)
            .values_list('tier').annotate(c=Count('id'))
        )
        pre = PreOrderReservation.objects.filter(
            config__seller=request.user, status='reserved',
        ).aggregate(s=Sum('quantity'))['s'] or 0
        back = BackorderRequest.objects.filter(
            config__seller=request.user, status='queued',
        ).aggregate(s=Sum('quantity'))['s'] or 0
        last_audit = InventoryAuditRun.objects.filter(
            seller=request.user, status='completed',
        ).order_by('-finished_at').first()
        return Response({
            'by_warehouse': list(wh_rows),
            'alerts_by_tier': alerts_by_tier,
            'preorder_units': pre,
            'backorder_units': back,
            'last_audit_accuracy': last_audit.accuracy_rate if last_audit else None,
        })
