"""
apps/analytics/seller_dashboard.py
───────────────────────────────────

Comprehensive seller analytics dashboard (R7).

What it exposes
───────────────
A single endpoint — ``GET /api/v1/analytics/seller/dashboard/`` —
returns one JSON document with every chart-worthy metric a seller
needs to run their store:

  • revenue       — daily revenue + order-count time series (configurable
                    window: 7, 30, 90, 365 days)
  • totals        — gross revenue, net revenue (after refunds), order
                    count, average order value, all for the window
  • funnel        — view → add_cart → checkout → purchase conversion
                    rates for the seller's products
  • top_products  — top 5 products by revenue + by units sold
  • status_breakdown — order-count by status (pending / confirmed /
                       shipped / delivered / cancelled / refunded)
  • geo           — top 5 cities by revenue
  • repeat_rate   — % of buyers in the window with > 1 order

Permissions
───────────
Seller (``is_seller=True``) or admin. A seller sees ONLY their own
data — every queryset filters by ``seller=request.user``. Admins
can pass ``?seller_id=N`` to inspect any seller (useful for support).

Why one endpoint, not seven
────────────────────────────
The dashboard renders all charts in one view. Seven round-trips would
add 1-2s of mobile-network latency on cold load — the single-endpoint
shape is one query budget. The view is heavy (~6 ORM queries) but
each is bounded + indexed.

Caching
───────
Per-seller, 5-minute cache via the response Cache-Control header.
Analytics doesn't need to be real-time — a 5-minute lag is invisible
to a seller checking their dashboard. Aggressive caching protects
the DB if a seller keeps refreshing.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsNotSuspended


# ─── Constants ────────────────────────────────────────────────────────

ALLOWED_WINDOW_DAYS = (7, 30, 90, 365)
DEFAULT_WINDOW_DAYS = 30

# Order statuses considered "real" revenue. Pending + cancelled are
# excluded from revenue totals (they haven't been paid and may never
# be); refunded is included in gross + subtracted from net.
REVENUE_STATUSES = (
    'confirmed', 'awaiting_seller', 'awaiting_ship',
    'shipped', 'delivered', 'completed',
)


# ─── View ─────────────────────────────────────────────────────────────

class SellerDashboardView(APIView):
    """``GET /api/v1/analytics/seller/dashboard/[?days=30][&seller_id=N]``"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        from apps.orders.models import Order

        # Resolve target seller. Admins may inspect any seller; everyone
        # else can only see their own data.
        seller = self._resolve_seller(request)
        if seller is None:
            return Response(
                {'error': 'forbidden', 'detail': 'Seller access required.'},
                status=403,
            )

        days = self._window_days(request)
        since = timezone.now() - timedelta(days=days)

        # Build all the pieces in a stable order so the response shape
        # is deterministic — important for clients that pin keys.
        orders = (
            Order.objects
            .filter(seller=seller, created_at__gte=since)
            .filter(is_deleted=False) if hasattr(Order, 'is_deleted')
            else Order.objects.filter(seller=seller, created_at__gte=since)
        )

        payload = OrderedDict()
        payload['window_days'] = days
        payload['seller_id'] = seller.pk
        payload['generated_at'] = timezone.now().isoformat()

        payload['totals'] = self._totals(orders)
        payload['revenue'] = self._revenue_series(orders, days)
        payload['status_breakdown'] = self._status_breakdown(orders)
        payload['top_products'] = self._top_products(seller, since)
        payload['geo'] = self._geo_breakdown(orders)
        payload['repeat_rate'] = self._repeat_buyer_rate(orders)
        payload['funnel'] = self._funnel(seller, since)

        response = Response(payload)
        # 5min CDN cache, per-user via the Vary header.
        response['Cache-Control'] = 'private, max-age=300'
        return response

    # ── Sub-computations ────────────────────────────────────────────

    def _resolve_seller(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u = request.user
        is_admin = bool(getattr(u, 'is_staff', False)
                        or getattr(u, 'is_superuser', False))
        seller_id = request.query_params.get('seller_id')
        if seller_id and is_admin:
            return User.objects.filter(pk=seller_id).first()
        if getattr(u, 'is_seller', False) or is_admin:
            return u
        return None

    def _window_days(self, request) -> int:
        try:
            d = int(request.query_params.get('days', DEFAULT_WINDOW_DAYS))
        except (TypeError, ValueError):
            d = DEFAULT_WINDOW_DAYS
        return d if d in ALLOWED_WINDOW_DAYS else DEFAULT_WINDOW_DAYS

    def _totals(self, orders) -> dict:
        """Single aggregate query for the headline numbers."""
        # Revenue subset: non-pending, non-cancelled.
        revenue_qs = orders.filter(status__in=REVENUE_STATUSES)
        gross = revenue_qs.aggregate(t=Sum('total'))['t'] or Decimal('0')
        order_count = revenue_qs.count()
        refunded = (
            orders
            .filter(status='refunded')
            .aggregate(t=Sum('total'))['t'] or Decimal('0')
        )
        net = gross - refunded
        aov = (gross / order_count) if order_count else Decimal('0')

        return {
            'gross_revenue': str(gross),
            'net_revenue':   str(net),
            'refunded':      str(refunded),
            'order_count':   order_count,
            'avg_order_value': str(aov.quantize(Decimal('0.01'))),
        }

    def _revenue_series(self, orders, days) -> list:
        """Daily revenue + order count for the past ``days``.

        Empty days are filled with zeros — important for the FE chart
        so the X-axis is continuous (Recharts won't auto-fill gaps).
        """
        rows = (
            orders
            .filter(status__in=REVENUE_STATUSES)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(
                revenue=Sum('total'),
                orders=Count('id'),
            )
            .order_by('day')
        )
        by_day = {r['day']: r for r in rows}

        today = timezone.now().date()
        out = []
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            r = by_day.get(d)
            out.append({
                'day': d.isoformat(),
                'revenue': str(r['revenue']) if r else '0',
                'orders': r['orders'] if r else 0,
            })
        return out

    def _status_breakdown(self, orders) -> dict:
        rows = (
            orders.values('status').annotate(n=Count('id')).order_by('-n')
        )
        return {r['status']: r['n'] for r in rows}

    def _top_products(self, seller, since) -> dict:
        """Top 5 by revenue + top 5 by units. Computed off OrderItem,
        not Order, because Order.total covers many items."""
        from apps.orders.models import OrderItem

        items = (
            OrderItem.objects
            .filter(
                order__seller=seller,
                order__created_at__gte=since,
                order__status__in=REVENUE_STATUSES,
            )
        )
        # Recent Django versions support F() in annotate; use unit_price
        # * quantity for revenue. OrderItem may name them differently —
        # be defensive about field presence.
        by_revenue = (
            items
            .values('product_id', 'product_title')
            .annotate(
                revenue=Sum(F('unit_price') * F('quantity')),
                units=Sum('quantity'),
            )
            .order_by('-revenue')[:5]
        )
        by_units = (
            items
            .values('product_id', 'product_title')
            .annotate(units=Sum('quantity'))
            .order_by('-units')[:5]
        )

        def shape(rows):
            return [
                {
                    'product_id': r['product_id'],
                    'title':      r['product_title'] or '',
                    'revenue':    str(r.get('revenue') or 0),
                    'units':      int(r.get('units') or 0),
                }
                for r in rows
            ]
        return {'by_revenue': shape(by_revenue), 'by_units': shape(by_units)}

    def _geo_breakdown(self, orders) -> list:
        """Top 5 cities by revenue. Skips empty shipping_city values."""
        rows = (
            orders
            .filter(status__in=REVENUE_STATUSES)
            .exclude(shipping_city='')
            .values('shipping_city')
            .annotate(
                revenue=Sum('total'),
                orders=Count('id'),
            )
            .order_by('-revenue')[:5]
        )
        return [
            {
                'city': r['shipping_city'],
                'revenue': str(r['revenue']),
                'orders': r['orders'],
            }
            for r in rows
        ]

    def _repeat_buyer_rate(self, orders) -> dict:
        """% of buyers in the window who placed > 1 order with this seller."""
        buyer_counts = (
            orders
            .filter(status__in=REVENUE_STATUSES)
            .values('buyer_id')
            .annotate(n=Count('id'))
        )
        total_buyers = 0
        repeat_buyers = 0
        for r in buyer_counts:
            total_buyers += 1
            if r['n'] > 1:
                repeat_buyers += 1
        rate = (
            (repeat_buyers / total_buyers * 100.0)
            if total_buyers else 0.0
        )
        return {
            'total_buyers': total_buyers,
            'repeat_buyers': repeat_buyers,
            'rate_pct': round(rate, 2),
        }

    def _funnel(self, seller, since) -> dict:
        """View → add_cart → checkout → purchase counts + conversion %.

        Sourced from FunnelEvent which the FE writes via the existing
        ``/track/`` endpoint. FunnelEvent.product carries the seller
        relationship transitively through Product.store.owner.
        """
        from apps.analytics.models import FunnelEvent
        out = OrderedDict()
        for event in ('view', 'add_cart', 'checkout', 'purchase'):
            n = (
                FunnelEvent.objects
                .filter(
                    event=event,
                    created_at__gte=since,
                    product__store__owner=seller,
                )
                .count()
            )
            out[event] = n
        view_n = out['view'] or 0
        purchase_n = out['purchase'] or 0
        conv = (purchase_n / view_n * 100.0) if view_n else 0.0
        return {
            'counts': dict(out),
            'view_to_purchase_pct': round(conv, 2),
        }
