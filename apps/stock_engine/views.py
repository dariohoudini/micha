"""Stock engine — REST endpoints under /api/v1/stock/."""
from django.db.models import F
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from . import state_machine as sm
from .models import (
    FlashStockPool, InventorySku, SkuReservation, StockEngineKpiSnapshot,
)


class IsSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (
            getattr(u, 'is_staff', False)
            or getattr(u, 'role', '') == 'seller' or u.stores.exists()))


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


# ── CH14 variant availability (buyer-facing) ──────────────────────────

class VariantAvailabilityView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        return Response({'variants':
                         services.variant_availability_matrix(product_id)})


# ── CH3/CH5 reserve (checkout) ────────────────────────────────────────

class ReserveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        items = request.data.get('items')
        order_id = request.data.get('order_id', '')
        try:
            if items:  # saga (multi-item)
                reservations = services.reserve_order_items(
                    order_id, [{'sku_id': i['sku_id'],
                                'quantity': int(i['quantity'])} for i in items],
                    payment_method=request.data.get('payment_method'))
                return Response({'reservations':
                                 [str(r.id) for r in reservations]},
                                status=status.HTTP_201_CREATED)
            res = services.reserve(
                request.data.get('sku_id'), int(request.data.get('quantity', 1)),
                reservation_type=request.data.get('reservation_type', 'checkout'),
                order_id=order_id, cart_id=request.data.get('cart_id', ''),
                payment_method=request.data.get('payment_method'),
                idempotency_key=request.headers.get('Idempotency-Key', ''))
            return Response({'reservation_id': str(res.id),
                             'expires_at': res.expires_at},
                            status=status.HTTP_201_CREATED)
        except sm.InsufficientStock as e:
            return Response({'error': 'insufficient_stock', 'sku_id': e.sku_id,
                             'requested': e.requested, 'available': e.available},
                            status=status.HTTP_409_CONFLICT)
        except sm.StockLockContention:
            return Response({'error': 'try_again'},
                            status=status.HTTP_423_LOCKED)


class ReservationExtendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, reservation_id):
        res = SkuReservation.objects.filter(id=reservation_id).first()
        if not res:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(services.extend_reservation(res))


class ReservationReleaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, reservation_id):
        res = SkuReservation.objects.filter(id=reservation_id).first()
        if not res:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        services.release(res, reason='buyer_cancelled')
        return Response({'released': True})


# ── CH15 notify-me ────────────────────────────────────────────────────

class NotifyMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, sku_id):
        sub = services.subscribe_restock(
            sku_id, user=request.user,
            email=request.data.get('email', '') or request.user.email)
        if sub is None:
            return Response({'error': 'sku not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'subscribed': True}, status=status.HTTP_201_CREATED)


# ── CH6 flash claim ───────────────────────────────────────────────────

class FlashClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pool_id):
        pool = FlashStockPool.objects.filter(id=pool_id).first()
        if not pool:
            return Response({'error': 'pool not found'},
                            status=status.HTTP_404_NOT_FOUND)
        result = services.claim_flash_stock(
            pool_id, request.user, int(request.data.get('quantity', 1)))
        code = status.HTTP_201_CREATED if result.get('ok') \
            else status.HTTP_409_CONFLICT
        return Response(result, status=code)


# ── CH8 bulk update (seller) ──────────────────────────────────────────

class BulkUpdateView(APIView):
    permission_classes = [IsSeller]

    def post(self, request):
        results = []
        for item in (request.data.get('items') or [])[:1000]:
            try:
                sku = services.bulk_update(
                    request.user, item['sku_id'],
                    change_type=item.get('change_type', 'set_to'),
                    value=int(item['value']))
                results.append({'sku_id': item['sku_id'],
                                'available': sku.available_quantity})
            except (ValueError, InventorySku.DoesNotExist) as exc:
                results.append({'sku_id': item.get('sku_id'),
                                'error': str(exc)})
        return Response({'results': results}, status=status.HTTP_201_CREATED)


# ── CH17 seller inventory health ──────────────────────────────────────

class InventoryHealthView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        qs = InventorySku.objects.filter(seller=request.user)
        total = qs.count()
        in_stock = qs.filter(available_quantity__gt=0).count()
        oos = qs.filter(available_quantity=0).count()
        low = qs.filter(available_quantity__gt=0,
                        available_quantity__lte=F('reorder_point')).count() \
            if total else 0
        return Response({
            'total_skus': total, 'in_stock': in_stock, 'oos': oos,
            'low_stock': low,
            'skus': [
                {'sku_id': str(s.id), 'sku_code': s.sku_code,
                 'available': s.available_quantity,
                 'reserved': s.reserved_quantity,
                 'committed': s.committed_quantity,
                 'reorder_point': s.reorder_point,
                 'health': ('green' if s.available_quantity > s.reorder_point
                            else 'red' if s.available_quantity < s.safety_stock_qty
                            else 'amber'),
                 'listing_status': s.listing_status}
                for s in qs[:200]]})


# ── CH24 KPIs ─────────────────────────────────────────────────────────

class KpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date, 'total_active_skus': s.total_active_skus,
             'in_stock_pct': str(s.in_stock_pct), 'oos_pct': str(s.oos_pct),
             'active_reservations': s.active_reservations,
             'reservation_conversion_pct': str(s.reservation_conversion_pct),
             'oversell_incidents': s.oversell_incidents,
             'integrity_exceptions': s.integrity_exceptions,
             'flash_pools_active': s.flash_pools_active}
            for s in StockEngineKpiSnapshot.objects.order_by(
                '-snapshot_date')[:30]]})

    def post(self, request):
        snap = services.snapshot_kpis()
        return Response({'date': snap.snapshot_date},
                        status=status.HTTP_201_CREATED)
