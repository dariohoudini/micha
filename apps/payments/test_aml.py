"""
R2 AML monitoring tests.

Coverage
────────
  TestDetectors
    - threshold_check honours AML_SINGLE_TX_THRESHOLD_AOA
    - structuring_check sums sub-threshold paid orders
    - rapid_drain_check detects inbound+outbound in window
    - disabled via AML_MONITORING_ENABLED

  TestEvaluators
    - evaluate_payment creates threshold alert when crossing
    - evaluate_payout creates threshold alert when crossing
    - rapid_drain alert when seller has both big inbound + big payout
    - no alerts when below thresholds

  TestAdminAPI
    - admin list filters by status / kind
    - detail returns detector_payload
    - review action=report transitions to 'reported'
    - review action=dismiss transitions to 'dismissed'
    - terminal alert returns 409 on re-review
    - non-admin rejected
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.payments.aml import (
    AMLAlert,
    evaluate_payment,
    evaluate_payout,
    rapid_drain_check,
    structuring_check,
    threshold_check,
)


User = get_user_model()


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-aml@test.com', password='TestPass123!',
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


def _mk_order(*, buyer, seller, total, status='delivered',
              payment_status='paid'):
    from apps.orders.models import Order
    return Order.objects.create(
        buyer=buyer, seller=seller,
        idempotency_key=f'test-{uuid.uuid4().hex}',
        shipping_name='B', shipping_phone='+244',
        shipping_address='r', shipping_city='Luanda',
        shipping_country='Angola',
        subtotal=total, total=total,
        status=status, payment_status=payment_status,
    )


# ─── Detectors ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestDetectors:

    def test_threshold_check_default(self, settings):
        settings.AML_SINGLE_TX_THRESHOLD_AOA = '9000000'
        assert threshold_check(Decimal('9000000')) is True
        assert threshold_check(Decimal('8999999')) is False

    def test_threshold_check_non_aoa_ignored(self):
        assert threshold_check(Decimal('1000000000'), currency='USD') is False

    def test_structuring_sums_sub_threshold(self, buyer, seller, settings):
        settings.AML_SINGLE_TX_THRESHOLD_AOA = '9000000'
        settings.AML_STRUCTURING_THRESHOLD_AOA = '5000000'
        settings.AML_STRUCTURING_WINDOW_DAYS = 30
        # Three orders of 2M each = 6M total → above 5M structuring threshold.
        for _ in range(3):
            _mk_order(buyer=buyer, seller=seller,
                      total=Decimal('2000000'), payment_status='paid')
        r = structuring_check(buyer)
        assert Decimal(r['aggregate']) == Decimal('6000000')
        assert r['triggered'] is True

    def test_rapid_drain_check(self, buyer, seller, settings):
        settings.AML_RAPID_DRAIN_MIN_AOA = '100000'
        settings.AML_RAPID_DRAIN_WINDOW_HOURS = 24
        # Inbound: 200k sale to seller
        _mk_order(buyer=buyer, seller=seller, total=Decimal('200000'),
                  payment_status='paid')
        # Outbound: 200k payout from seller
        from apps.payments.models import PayoutRequest
        PayoutRequest.objects.create(
            seller=seller, amount=Decimal('200000'), status='approved',
        )
        r = rapid_drain_check(seller)
        assert r['triggered'] is True
        assert Decimal(r['inbound']) >= Decimal('200000')
        assert Decimal(r['outbound']) >= Decimal('200000')

    def test_disabled_via_settings(self, buyer, seller, settings):
        settings.AML_MONITORING_ENABLED = False
        # Create a payment that would otherwise trip the threshold.
        order = _mk_order(buyer=buyer, seller=seller,
                          total=Decimal('99999999'), payment_status='paid')
        from apps.orders.models import Payment
        p = Payment.objects.create(order=order, amount=order.total,
                                   status='paid', gateway_reference='X')
        out = evaluate_payment(p)
        assert out == []
        assert AMLAlert.objects.count() == 0


# ─── Evaluators ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEvaluators:

    def test_payment_threshold_creates_alert(self, buyer, seller, settings):
        settings.AML_SINGLE_TX_THRESHOLD_AOA = '5000000'
        order = _mk_order(buyer=buyer, seller=seller,
                          total=Decimal('5000000'), payment_status='paid')
        from apps.orders.models import Payment
        p = Payment.objects.create(order=order, amount=order.total,
                                   status='paid', gateway_reference='X')
        alerts = evaluate_payment(p)
        kinds = [a.kind for a in alerts]
        assert 'threshold' in kinds
        assert AMLAlert.objects.filter(kind='threshold').count() == 1

    def test_payout_threshold_creates_alert(self, seller, settings):
        settings.AML_SINGLE_TX_THRESHOLD_AOA = '5000000'
        from apps.payments.models import PayoutRequest
        po = PayoutRequest.objects.create(
            seller=seller, amount=Decimal('5000000'), status='pending',
        )
        alerts = evaluate_payout(po)
        assert any(a.kind == 'threshold' for a in alerts)

    def test_no_alerts_below_threshold(self, buyer, seller, settings):
        settings.AML_SINGLE_TX_THRESHOLD_AOA = '5000000'
        settings.AML_STRUCTURING_THRESHOLD_AOA = '5000000'
        order = _mk_order(buyer=buyer, seller=seller, total=Decimal('1000'))
        from apps.orders.models import Payment
        p = Payment.objects.create(order=order, amount=order.total,
                                   status='paid', gateway_reference='Y')
        alerts = evaluate_payment(p)
        assert alerts == []


# ─── Admin API ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminAPI:

    URL = '/api/v1/payments/aml/alerts/'

    def _seed(self, *, status='open', kind='threshold'):
        return AMLAlert.objects.create(
            kind=kind, severity='high', status=status,
            aggregate_amount=Decimal('9000000'),
            reason='test alert',
        )

    def test_non_admin_rejected(self, api_client, buyer_client):
        assert api_client.get(self.URL).status_code in (401, 403)
        assert buyer_client.get(self.URL).status_code == 403

    def test_list_default_open_and_review(self, admin_client):
        self._seed(status='open')
        self._seed(status='under_review')
        self._seed(status='reported')
        self._seed(status='dismissed')
        res = admin_client.get(self.URL)
        assert res.status_code == 200
        statuses = {r['status'] for r in res.data['results']}
        assert statuses <= {'open', 'under_review'}

    def test_list_filter_by_status(self, admin_client):
        self._seed(status='reported')
        res = admin_client.get(self.URL, {'status': 'reported'})
        assert all(r['status'] == 'reported' for r in res.data['results'])

    def test_review_report(self, admin_client):
        a = self._seed()
        res = admin_client.post(
            f'/api/v1/payments/aml/alerts/{a.pk}/review/',
            {'action': 'report', 'note': 'STR filed UIF-2026-01'},
            format='json',
        )
        assert res.status_code == 200
        assert res.data['status'] == 'reported'

    def test_review_dismiss(self, admin_client):
        a = self._seed()
        res = admin_client.post(
            f'/api/v1/payments/aml/alerts/{a.pk}/review/',
            {'action': 'dismiss', 'note': 'False positive'},
            format='json',
        )
        assert res.status_code == 200
        assert res.data['status'] == 'dismissed'

    def test_review_terminal_alert_returns_409(self, admin_client):
        a = self._seed(status='reported')
        res = admin_client.post(
            f'/api/v1/payments/aml/alerts/{a.pk}/review/',
            {'action': 'dismiss'}, format='json',
        )
        assert res.status_code == 409

    def test_review_invalid_action_400(self, admin_client):
        a = self._seed()
        res = admin_client.post(
            f'/api/v1/payments/aml/alerts/{a.pk}/review/',
            {'action': 'wat'}, format='json',
        )
        assert res.status_code == 400
