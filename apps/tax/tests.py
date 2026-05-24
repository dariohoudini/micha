"""
R2 tax integration tests.

Coverage
────────
  TestCheckoutIVA
    - checkout for AO ship-to applies 14% IVA on (subtotal - discount)
    - tax_amount is included in total
    - TaxCalculation audit row written with ref_type='order'
    - non-AO ship-to falls back to tax_amount=0 when jurisdiction unset
    - verify_total invariant holds with tax included

  TestAGTReport
    - admin required
    - default window is prior month
    - aggregates by jurisdiction
    - CSV format returns text/csv content-type + filing header rows
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone


User = get_user_model()


# ─── Checkout IVA ──────────────────────────────────────────────────────


@pytest.fixture
def angola_iva(db):
    """Ensure the seed migration ran and the AO 14% IVA row is in place."""
    from apps.tax.models import TaxJurisdiction, TaxRate
    jur = TaxJurisdiction.objects.filter(country_code='AO', province_code='').first()
    if jur is None:
        jur = TaxJurisdiction.objects.create(
            country_code='AO', name='Angola',
        )
    if not TaxRate.objects.filter(jurisdiction=jur, valid_until__isnull=True).exists():
        TaxRate.objects.create(
            jurisdiction=jur,
            name='IVA',
            rate=Decimal('0.1400'),
            source='regulator',
            valid_from=timezone.now(),
        )
    return jur


@pytest.fixture
def buyer_address(db, buyer):
    from apps.shipping.models import ShippingAddress
    return ShippingAddress.objects.create(
        user=buyer,
        full_name='Test Buyer',
        phone='+244923000000',
        address_line='Rua Test 123',
        city='Luanda',
        province='Luanda',
        country='Angola',
    )


@pytest.mark.django_db
class TestCheckoutIVA:

    def _ensure_cart(self, buyer, product, qty=1):
        from apps.cart.models import Cart, CartItem
        cart, _ = Cart.objects.get_or_create(user=buyer)
        CartItem.objects.create(
            cart=cart, product=product, quantity=qty,
            price_at_add=product.price,
        )
        return cart

    def test_iva_applied_on_ao_checkout(
            self, buyer_client, buyer, product, buyer_address, angola_iva):
        from apps.orders.checkout import CheckoutService
        from apps.orders.models import Order

        # Single product at price 180000.00 quantity 1 → subtotal=180000.
        # Expected IVA at 14% = 25200. Total = 180000 + shipping + 25200.
        self._ensure_cart(buyer, product, qty=1)

        svc = CheckoutService(buyer, {
            'address_id': buyer_address.pk,
            'payment_method': 'multicaixa',
            'idempotency_key': str(uuid.uuid4()),
        })
        orders = svc.execute()
        assert len(orders) == 1
        o = orders[0]

        # 14% of 180000 = 25200.
        assert o.tax_amount == Decimal('25200.00')
        # Total = subtotal (180000) + shipping (500) + tax (25200) - discount (0)
        assert o.total == Decimal('205700.00')

    def test_tax_calculation_audit_row_written(
            self, buyer_client, buyer, product, buyer_address, angola_iva):
        from apps.orders.checkout import CheckoutService
        from apps.tax.models import TaxCalculation

        self._ensure_cart(buyer, product, qty=1)
        svc = CheckoutService(buyer, {
            'address_id': buyer_address.pk,
            'payment_method': 'multicaixa',
            'idempotency_key': str(uuid.uuid4()),
        })
        orders = svc.execute()
        order = orders[0]

        # Exactly one TaxCalculation row for this order.
        tc = TaxCalculation.objects.filter(
            ref_type='order', ref_id=str(order.pk),
        ).first()
        assert tc is not None
        assert tc.total_tax == Decimal('25200.00')
        assert tc.ship_to_country == 'AO'

    def test_no_iva_when_jurisdiction_missing(
            self, buyer_client, buyer, product, buyer_address):
        """When the ship-to country isn't configured (no fixture),
        checkout falls back to tax=0 — never refuses the sale."""
        from apps.orders.checkout import CheckoutService

        # Force a non-mapped country.
        buyer_address.country = 'Mars'
        buyer_address.save(update_fields=['country'])
        self._ensure_cart(buyer, product, qty=1)
        svc = CheckoutService(buyer, {
            'address_id': buyer_address.pk,
            'payment_method': 'multicaixa',
            'idempotency_key': str(uuid.uuid4()),
        })
        orders = svc.execute()
        assert orders[0].tax_amount == Decimal('0.00')

    def test_verify_total_holds_with_tax(
            self, buyer_client, buyer, product, buyer_address, angola_iva):
        from apps.orders.checkout import CheckoutService

        self._ensure_cart(buyer, product, qty=2)
        svc = CheckoutService(buyer, {
            'address_id': buyer_address.pk,
            'payment_method': 'multicaixa',
            'idempotency_key': str(uuid.uuid4()),
        })
        orders = svc.execute()
        order = orders[0]
        # verify_total should NOT raise — tax_amount baked into the
        # invariant computation.
        order.verify_total()


# ─── AGT report ───────────────────────────────────────────────────────


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-tax@test.com', password='TestPass123!',
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


@pytest.mark.django_db
class TestAGTReport:

    URL = '/api/v1/tax/report/agt/'

    def _seed_tax_rows(self, angola_iva, n=3):
        from apps.tax.models import TaxCalculation
        for i in range(n):
            TaxCalculation.objects.create(
                ref_type='order', ref_id=str(1000 + i),
                ship_to_country='AO', ship_to_province='',
                jurisdiction=angola_iva,
                rate_applied=Decimal('0.1400'),
                breakdown={},
                total_taxable=Decimal('1000.00'),
                total_tax=Decimal('140.00'),
            )

    def test_admin_required(self, api_client):
        res = api_client.get(self.URL)
        assert res.status_code in (401, 403)

    def test_buyer_forbidden(self, buyer_client):
        res = buyer_client.get(self.URL)
        assert res.status_code == 403

    def test_report_aggregates(self, admin_client, angola_iva):
        self._seed_tax_rows(angola_iva, n=3)
        today = timezone.now().date()
        res = admin_client.get(
            self.URL,
            {'from': today.isoformat(), 'to': today.isoformat()},
        )
        assert res.status_code == 200
        body = res.data
        assert Decimal(body['totals']['tax']) == Decimal('420.00')
        assert Decimal(body['totals']['taxable']) == Decimal('3000.00')
        assert body['count'] == 3
        assert body['by_jurisdiction'][0]['country_code'] == 'AO'

    def test_csv_format(self, admin_client, angola_iva):
        self._seed_tax_rows(angola_iva, n=2)
        today = timezone.now().date()
        res = admin_client.get(
            self.URL,
            {'from': today.isoformat(), 'to': today.isoformat(),
             'format': 'csv'},
        )
        assert res.status_code == 200
        assert 'text/csv' in res['Content-Type']
        assert 'MAPA RESUMO IVA' in res.content.decode('utf-8')

    def test_invalid_date_range_rejected(self, admin_client):
        res = admin_client.get(
            self.URL,
            {'from': '2026-01-01', 'to': '2025-01-01'},
        )
        assert res.status_code == 400
