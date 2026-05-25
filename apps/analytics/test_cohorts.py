"""R7 cohort retention tests."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.analytics.cohorts import build_cohort_retention


User = get_user_model()


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-cohort@test.com', password='TestPass123!',
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


def _mk_order(buyer, seller, at):
    from apps.orders.models import Order
    o = Order.objects.create(
        buyer=buyer, seller=seller,
        idempotency_key=f't-{uuid.uuid4().hex}',
        shipping_name='b', shipping_phone='+244',
        shipping_address='r', shipping_city='Luanda',
        shipping_country='Angola',
        subtotal=Decimal('100'), total=Decimal('100'),
        status='delivered', payment_status='paid',
    )
    Order.objects.filter(pk=o.pk).update(created_at=at)
    return o


@pytest.mark.django_db
class TestCohortRetention:

    def test_w0_baseline_matches_cohort_size(self, seller):
        # Create 3 users this week. No orders.
        from datetime import datetime
        for i in range(3):
            u = User.objects.create_user(
                email=f'c-{i}@test.com', password='x',
                is_email_verified=True, status='active',
            )
        rows = build_cohort_retention(weeks=4)
        assert any(r['retention']['w0'] >= 3 for r in rows)

    def test_w1_counts_returning_user(self, seller):
        now = timezone.now()
        u = User.objects.create_user(
            email='ret@test.com', password='x',
            is_email_verified=True, status='active',
        )
        User.objects.filter(pk=u.pk).update(date_joined=now - timedelta(days=10))

        # Order placed in week 1 (8-14 days later).
        _mk_order(u, seller, now - timedelta(days=3))
        rows = build_cohort_retention(weeks=4)
        # Some row has w1 >= 1 for this user.
        assert any(r['retention'].get('w1', 0) >= 1 for r in rows)

    def test_admin_endpoint(self, admin_client):
        res = admin_client.get('/api/v1/analytics/cohorts/?weeks=4')
        assert res.status_code == 200
        assert 'cohorts' in res.data
        assert res.data['cohort_size_weeks'] == 4

    def test_non_admin_rejected(self, api_client, buyer_client):
        url = '/api/v1/analytics/cohorts/'
        assert api_client.get(url).status_code in (401, 403)
        assert buyer_client.get(url).status_code == 403
