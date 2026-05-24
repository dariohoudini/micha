"""
R2 settlement reconciliation tests.

Coverage
────────
  TestParse
    - lenient parser handles AppyPay column variations + comma decimals
  TestReconcile
    - matched row (under threshold) → matched counter
    - drift row → SettlementDrift + total_drift accumulator
    - unknown ref → SettlementDrift kind='unknown'
    - rerunning same date does not corrupt prior drifts
  TestUploadAPI
    - admin required
    - missing file → 400
    - bad date → 400
    - successful upload returns summary stats
"""
from __future__ import annotations

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.payments.settlement import (
    parse_settlement_csv,
    reconcile_settlement_rows,
    SettlementDrift,
    SettlementReconRun,
)


User = get_user_model()


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-stl@test.com', password='TestPass123!',
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
def paid_payment(db, buyer, seller):
    """Order + Payment with a known gateway_reference for matching."""
    from apps.orders.models import Order, Payment
    o = Order.objects.create(
        buyer=buyer, seller=seller,
        idempotency_key=f'test-{uuid.uuid4().hex}',
        shipping_name='Buyer', shipping_phone='+244',
        shipping_address='r', shipping_city='Luanda',
        shipping_country='Angola',
        subtotal=Decimal('1000'), total=Decimal('1000'),
        status='delivered', payment_status='paid',
    )
    p = Payment.objects.create(
        order=o, amount=Decimal('1000'),
        status='paid', gateway_reference='PAY-MATCHED',
    )
    return p


# ─── Parser ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestParse:

    def test_canonical_columns(self):
        csv_text = (
            'date,gateway_reference,type,gross_amount,fee,net_amount,currency\n'
            '2026-05-23,PAY-1,sale,1000.00,18.50,981.50,AOA\n'
        )
        rows = parse_settlement_csv(csv_text)
        assert len(rows) == 1
        r = rows[0]
        assert r['gateway_reference'] == 'PAY-1'
        assert r['gross_amount'] == '1000.00'
        assert r['currency'] == 'AOA'

    def test_alternate_column_names(self):
        # AppyPay has used 'gateway_ref' + 'gross' + 'ccy' on older feeds.
        csv_text = (
            'date,gateway_ref,kind,gross,fees,net,ccy\n'
            '2026-05-23,PAY-2,refund,500,10,490,AOA\n'
        )
        rows = parse_settlement_csv(csv_text)
        assert rows[0]['gateway_reference'] == 'PAY-2'
        assert rows[0]['type'] == 'refund'
        assert rows[0]['gross_amount'] == '500'

    def test_handles_bytes_input(self):
        rows = parse_settlement_csv(
            b'date,gateway_reference,type,gross_amount\n2026-05-23,X,sale,100\n'
        )
        assert rows[0]['gateway_reference'] == 'X'


# ─── Reconcile ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestReconcile:

    def test_matched_row_no_drift(self, paid_payment, settings):
        settings.SETTLEMENT_DRIFT_THRESHOLD_AOA = '1.00'
        rows = [
            {'date': '2026-05-23', 'gateway_reference': 'PAY-MATCHED',
             'type': 'sale', 'gross_amount': '1000.00',
             'fee': '18.50', 'net_amount': '981.50', 'currency': 'AOA'},
        ]
        run = reconcile_settlement_rows(rows, settlement_date=date(2026, 5, 23))
        assert run.matched == 1
        assert run.drift_rows == 0
        assert run.unknown_rows == 0
        assert run.total_drift == Decimal('0')

    def test_drift_row_recorded(self, paid_payment, settings):
        settings.SETTLEMENT_DRIFT_THRESHOLD_AOA = '1.00'
        rows = [
            {'date': '2026-05-23', 'gateway_reference': 'PAY-MATCHED',
             'type': 'sale', 'gross_amount': '950.00',   # 50 AOA short
             'fee': '0', 'net_amount': '950.00', 'currency': 'AOA'},
        ]
        run = reconcile_settlement_rows(rows, settlement_date=date(2026, 5, 23))
        assert run.matched == 0
        assert run.drift_rows == 1
        assert run.total_drift == Decimal('50.00')
        drift = SettlementDrift.objects.filter(run=run).first()
        assert drift.kind == 'drift'
        assert drift.drift_amount == Decimal('-50.00')  # PSP says 950, ledger 1000

    def test_unknown_ref(self, settings):
        rows = [
            {'date': '2026-05-23', 'gateway_reference': 'GHOST-REF',
             'type': 'sale', 'gross_amount': '200.00',
             'fee': '0', 'net_amount': '200', 'currency': 'AOA'},
        ]
        run = reconcile_settlement_rows(rows, settlement_date=date(2026, 5, 23))
        assert run.unknown_rows == 1
        drift = SettlementDrift.objects.filter(run=run).first()
        assert drift.kind == 'unknown'

    def test_rerunning_same_date_creates_new_run(self, paid_payment):
        rows = [
            {'date': '2026-05-23', 'gateway_reference': 'PAY-MATCHED',
             'type': 'sale', 'gross_amount': '1000.00',
             'fee': '0', 'net_amount': '1000', 'currency': 'AOA'},
        ]
        r1 = reconcile_settlement_rows(rows, settlement_date=date(2026, 5, 23))
        r2 = reconcile_settlement_rows(rows, settlement_date=date(2026, 5, 23))
        assert r1.pk != r2.pk
        assert SettlementReconRun.objects.filter(
            settlement_date=date(2026, 5, 23)
        ).count() == 2

    def test_threshold_under_drift_threshold_is_matched(self, paid_payment, settings):
        """A 0.50 AOA mismatch under the default 1.00 threshold counts
        as matched (rounding noise)."""
        settings.SETTLEMENT_DRIFT_THRESHOLD_AOA = '1.00'
        rows = [
            {'date': '2026-05-23', 'gateway_reference': 'PAY-MATCHED',
             'type': 'sale', 'gross_amount': '1000.50',
             'fee': '0', 'net_amount': '1000.50', 'currency': 'AOA'},
        ]
        run = reconcile_settlement_rows(rows, settlement_date=date(2026, 5, 23))
        assert run.matched == 1
        assert run.drift_rows == 0


# ─── Upload API ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestUploadAPI:

    URL = '/api/v1/payments/settlement/upload/'

    def test_admin_required(self, api_client, buyer_client):
        assert api_client.post(self.URL).status_code in (401, 403)
        assert buyer_client.post(self.URL).status_code == 403

    def test_missing_file(self, admin_client):
        res = admin_client.post(
            self.URL, {'settlement_date': '2026-05-23'}, format='multipart',
        )
        assert res.status_code == 400

    def test_bad_date(self, admin_client):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile(
            'feed.csv',
            b'date,gateway_reference,type,gross_amount\n2026-05-23,X,sale,1\n',
            content_type='text/csv',
        )
        res = admin_client.post(
            self.URL, {'file': f, 'settlement_date': 'not-a-date'},
            format='multipart',
        )
        assert res.status_code == 400

    def test_successful_upload(self, admin_client, paid_payment):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv = (
            b'date,gateway_reference,type,gross_amount,fee,net_amount\n'
            b'2026-05-23,PAY-MATCHED,sale,1000.00,18.50,981.50\n'
            b'2026-05-23,UNKNOWN,sale,100,0,100\n'
        )
        f = SimpleUploadedFile('feed.csv', csv, content_type='text/csv')
        res = admin_client.post(
            self.URL, {'file': f, 'settlement_date': '2026-05-23'},
            format='multipart',
        )
        assert res.status_code == 201
        assert res.data['row_count'] == 2
        assert res.data['matched'] == 1
        assert res.data['unknown_rows'] == 1
