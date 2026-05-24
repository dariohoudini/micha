"""
R7 seller analytics dashboard tests.

Coverage
────────
  TestSellerDashboardAuth
    - anonymous → 401
    - regular buyer → 403 (no is_seller, no is_staff)
    - seller → 200 with their own data
    - admin can use ?seller_id=N to inspect

  TestSellerDashboardShape
    - all top-level keys present
    - revenue series length matches window_days
    - days outside ALLOWED_WINDOW_DAYS coerced to default 30
    - totals computed correctly with sample data
    - status_breakdown counts only this seller's orders
    - top_products ordered by revenue
    - repeat-buyer rate maths
    - cache-control header set
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone


User = get_user_model()
DASHBOARD_URL = '/api/v1/analytics/seller/dashboard/'


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin@test.com', password='TestPass123!',
        is_email_verified=True, status='active',
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def admin_client(admin):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    c = APIClient()
    refresh = RefreshToken.for_user(admin)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return c


@pytest.fixture
def another_seller(db):
    return User.objects.create_user(
        email='seller2@test.com', password='TestPass123!',
        is_email_verified=True, is_seller=True, is_verified_seller=True,
        status='active',
    )


_order_counter = {'n': 0}


def _make_order(seller, buyer, *, status='delivered', total=Decimal('1000'),
                created_ago_days=1, shipping_city='Luanda'):
    """Create an Order in the past — bypassing auto_now_add.

    Each call uses a fresh idempotency_key so the unique constraint
    doesn't fire when a test creates multiple orders for the same
    buyer/seller pair.
    """
    from apps.orders.models import Order
    import uuid
    _order_counter['n'] += 1
    target = timezone.now() - timedelta(days=created_ago_days)
    order = Order.objects.create(
        seller=seller, buyer=buyer,
        subtotal=total, total=total,
        status=status, payment_status='paid',
        shipping_city=shipping_city,
        idempotency_key=f'test-{uuid.uuid4().hex}',
    )
    Order.objects.filter(pk=order.pk).update(created_at=target)
    order.refresh_from_db()
    return order


def _make_order_item(order, product, *, quantity=1, unit_price=None):
    from apps.orders.models import OrderItem
    return OrderItem.objects.create(
        order=order, product=product,
        product_title=product.title,
        unit_price=unit_price or product.price,
        quantity=quantity,
    )


# ─── Auth ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSellerDashboardAuth:

    def test_anonymous_rejected(self, api_client):
        res = api_client.get(DASHBOARD_URL)
        assert res.status_code in (401, 403)

    def test_buyer_rejected(self, buyer_client):
        res = buyer_client.get(DASHBOARD_URL)
        assert res.status_code == 403

    def test_seller_can_view(self, seller_client, seller):
        res = seller_client.get(DASHBOARD_URL)
        assert res.status_code == 200
        assert res.data['seller_id'] == seller.pk

    def test_admin_can_inspect_other_seller(
            self, admin_client, another_seller):
        res = admin_client.get(
            DASHBOARD_URL, {'seller_id': another_seller.pk}
        )
        assert res.status_code == 200
        assert res.data['seller_id'] == another_seller.pk


# ─── Shape ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSellerDashboardShape:

    def test_all_top_level_keys_present(self, seller_client):
        res = seller_client.get(DASHBOARD_URL)
        body = res.data
        for k in ('window_days', 'seller_id', 'generated_at',
                  'totals', 'revenue', 'status_breakdown',
                  'top_products', 'geo', 'repeat_rate', 'funnel'):
            assert k in body, f'missing key: {k}'

    def test_revenue_series_length_matches_window(self, seller_client):
        res = seller_client.get(DASHBOARD_URL, {'days': 7})
        assert len(res.data['revenue']) == 7
        assert res.data['window_days'] == 7

    def test_invalid_window_coerced_to_default(self, seller_client):
        # Not in ALLOWED_WINDOW_DAYS → falls back to 30.
        res = seller_client.get(DASHBOARD_URL, {'days': 13})
        assert res.data['window_days'] == 30

    def test_totals_match_orders(self, seller_client, seller, buyer, product):
        _make_order(seller, buyer, status='delivered',
                    total=Decimal('1000'), created_ago_days=1)
        _make_order(seller, buyer, status='delivered',
                    total=Decimal('500'), created_ago_days=2)
        # Cancelled order — should NOT count toward revenue.
        _make_order(seller, buyer, status='cancelled',
                    total=Decimal('999'), created_ago_days=2)
        # Refunded — counts in gross but subtracted from net.
        _make_order(seller, buyer, status='refunded',
                    total=Decimal('200'), created_ago_days=3)

        res = seller_client.get(DASHBOARD_URL, {'days': 30})
        t = res.data['totals']
        # gross = 1000 + 500 (delivered), refunded = 200, net = gross - refunded
        assert Decimal(t['gross_revenue']) == Decimal('1500')
        assert Decimal(t['net_revenue']) == Decimal('1300')
        assert Decimal(t['refunded']) == Decimal('200')
        assert t['order_count'] == 2

    def test_status_breakdown_only_this_sellers_orders(
            self, seller_client, seller, another_seller, buyer):
        _make_order(seller, buyer, status='delivered')
        _make_order(seller, buyer, status='pending')
        _make_order(another_seller, buyer, status='delivered')  # foreign

        res = seller_client.get(DASHBOARD_URL)
        sb = res.data['status_breakdown']
        # Only counts this seller's 2 orders.
        assert sum(sb.values()) == 2

    def test_top_products_ordered_by_revenue(
            self, seller_client, seller, buyer, product, category, store):
        from apps.products.models import Product

        p1 = product
        p2 = Product.objects.create(
            store=store, title='Cheap', slug='cheap',
            price=Decimal('10'), category=category, quantity=100,
            is_active=True,
        )
        o = _make_order(seller, buyer, status='delivered',
                        total=Decimal('1000'))
        _make_order_item(o, p1, quantity=2, unit_price=Decimal('500'))
        _make_order_item(o, p2, quantity=10, unit_price=Decimal('10'))

        res = seller_client.get(DASHBOARD_URL)
        by_rev = res.data['top_products']['by_revenue']
        assert by_rev[0]['product_id'] == p1.pk
        assert by_rev[0]['units'] == 2

        by_units = res.data['top_products']['by_units']
        assert by_units[0]['product_id'] == p2.pk
        assert by_units[0]['units'] == 10

    def test_repeat_buyer_rate(self, seller_client, seller, buyer, product):
        """One repeat buyer (2 orders) + one solo buyer = 50% repeat rate."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        buyer2 = User.objects.create_user(
            email='b2@test.com', password='TestPass123!',
            is_email_verified=True, status='active',
        )
        _make_order(seller, buyer, status='delivered')
        _make_order(seller, buyer, status='delivered')
        _make_order(seller, buyer2, status='delivered')

        res = seller_client.get(DASHBOARD_URL)
        r = res.data['repeat_rate']
        assert r['total_buyers'] == 2
        assert r['repeat_buyers'] == 1
        assert r['rate_pct'] == 50.0

    def test_cache_control_set(self, seller_client):
        res = seller_client.get(DASHBOARD_URL)
        cc = res.get('Cache-Control', '')
        assert 'private' in cc or 'max-age' in cc

    def test_geo_breakdown_excludes_empty_city(
            self, seller_client, seller, buyer, product):
        _make_order(seller, buyer, status='delivered',
                    total=Decimal('1000'), shipping_city='Luanda')
        _make_order(seller, buyer, status='delivered',
                    total=Decimal('500'), shipping_city='')

        res = seller_client.get(DASHBOARD_URL)
        cities = [g['city'] for g in res.data['geo']]
        assert 'Luanda' in cities
        assert '' not in cities
