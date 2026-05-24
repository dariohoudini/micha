"""
R2 chargeback workflow tests.

Coverage
────────
  TestIngest
    - new external_case_id → row created + evidence packet assembled
    - duplicate external_case_id → returns existing row (idempotent)
    - default deadline = received + 7 days

  TestTransitions
    - submit_evidence: received → evidence
    - accept_loss: received → accepted
    - resolve: evidence → won / lost
    - invalid transitions raise ValueError
    - is_overdue() respects deadline + status

  TestAdminAPI
    - admin list / filter by status / overdue
    - admin detail returns evidence packet
    - respond / accept / resolve endpoints + state checks
    - non-admin → 403

  TestInboundWebhook
    - admin can paste a chargeback (no HMAC, just admin auth)
    - missing fields → 400
    - unknown payment_id → 404
    - duplicate external_case_id → 200 + existing row
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.payments.chargebacks import (
    Chargeback,
    accept_loss,
    ingest_chargeback,
    resolve as resolve_cb,
    submit_evidence,
)


User = get_user_model()


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-cb@test.com', password='TestPass123!',
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
def order_with_payment(db, buyer, seller):
    """Realistic Order + Payment fixture for evidence-packet tests."""
    from apps.orders.models import Order, Payment
    o = Order.objects.create(
        buyer=buyer, seller=seller,
        idempotency_key=f'test-{uuid.uuid4().hex}',
        shipping_name='Test Buyer', shipping_phone='+244923000000',
        shipping_address='Rua Test 1', shipping_city='Luanda',
        shipping_country='Angola',
        subtotal=Decimal('1000'), total=Decimal('1000'),
        status='delivered', payment_status='paid',
    )
    p = Payment.objects.create(
        order=o, amount=Decimal('1000'), status='paid',
        gateway_reference=f'pay-{uuid.uuid4().hex[:12]}',
    )
    return o, p


# ─── Ingest ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestIngest:

    def test_new_case_creates_row_and_packet(self, order_with_payment):
        _, payment = order_with_payment
        cb = ingest_chargeback(
            external_case_id='PSP-001',
            payment=payment,
            amount=Decimal('1000'),
            reason_code='fraud',
            reason_text='card holder denies transaction',
        )
        assert cb.pk
        assert cb.status == 'received'
        # Evidence packet has the order, items, payment.
        assert 'order' in cb.evidence_packet
        assert 'payment' in cb.evidence_packet
        assert cb.evidence_packet['payment']['gateway_reference'] == payment.gateway_reference

    def test_duplicate_case_id_returns_existing(self, order_with_payment):
        _, payment = order_with_payment
        a = ingest_chargeback(
            external_case_id='PSP-002', payment=payment, amount=Decimal('500'),
        )
        b = ingest_chargeback(
            external_case_id='PSP-002', payment=payment, amount=Decimal('500'),
        )
        assert a.pk == b.pk
        assert Chargeback.objects.filter(external_case_id='PSP-002').count() == 1

    def test_default_deadline_is_seven_days_out(self, order_with_payment):
        _, payment = order_with_payment
        cb = ingest_chargeback(
            external_case_id='PSP-003', payment=payment, amount=Decimal('100'),
        )
        delta = cb.deadline_at - cb.received_at
        # Allow tiny clock drift between received_at (auto_now_add) and
        # deadline_at (computed in Python).
        assert timedelta(days=6, hours=23) <= delta <= timedelta(days=7, minutes=1)


# ─── Transitions ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTransitions:

    def _fresh(self, payment, **kw):
        return ingest_chargeback(
            external_case_id=kw.pop('case', f'PSP-{uuid.uuid4().hex[:8]}'),
            payment=payment,
            amount=kw.pop('amount', Decimal('100')),
            **kw,
        )

    def test_submit_evidence_transitions_state(self, order_with_payment, admin):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        out = submit_evidence(cb, evidence={'proof': 'tracking-12345'}, actor=admin)
        assert out.status == 'evidence'
        assert out.handled_by == admin
        assert out.responded_at is not None
        # Admin submission appended to evidence_packet.
        subs = out.evidence_packet.get('admin_submissions', [])
        assert len(subs) == 1
        assert subs[0]['submitted_by'] == admin.email

    def test_accept_loss_transitions_state(self, order_with_payment, admin):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        out = accept_loss(cb, actor=admin, note='Not worth fighting')
        assert out.status == 'accepted'
        assert out.resolved_at is not None
        assert 'Not worth fighting' in out.admin_notes

    def test_resolve_won_from_evidence_state(self, order_with_payment, admin):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        cb = submit_evidence(cb, evidence={'a': 1}, actor=admin)
        out = resolve_cb(cb, won=True, actor=admin)
        assert out.status == 'won'

    def test_resolve_lost_from_evidence_state(self, order_with_payment, admin):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        cb = submit_evidence(cb, evidence={'a': 1}, actor=admin)
        out = resolve_cb(cb, won=False, actor=admin)
        assert out.status == 'lost'

    def test_invalid_submit_after_resolved_raises(self, order_with_payment, admin):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        cb = submit_evidence(cb, evidence={'a': 1}, actor=admin)
        resolve_cb(cb, won=True, actor=admin)
        with pytest.raises(ValueError):
            submit_evidence(cb, evidence={'b': 2}, actor=admin)

    def test_resolve_from_received_state_raises(self, order_with_payment, admin):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        # Cannot resolve before submitting evidence (would skip the
        # evidence stage of the workflow).
        with pytest.raises(ValueError):
            resolve_cb(cb, won=True, actor=admin)

    def test_is_overdue(self, order_with_payment):
        _, payment = order_with_payment
        cb = self._fresh(payment)
        Chargeback.objects.filter(pk=cb.pk).update(
            deadline_at=timezone.now() - timedelta(days=1),
        )
        cb.refresh_from_db()
        assert cb.is_overdue() is True
        # Resolving clears overdue status (no longer 'received').
        cb.status = 'evidence'
        assert cb.is_overdue() is False


# ─── Admin API ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminAPI:

    def test_list_requires_admin(self, api_client, buyer_client):
        assert api_client.get('/api/v1/payments/chargebacks/').status_code in (401, 403)
        assert buyer_client.get('/api/v1/payments/chargebacks/').status_code == 403

    def test_list_filters_status(self, admin_client, order_with_payment):
        _, payment = order_with_payment
        a = ingest_chargeback(external_case_id='LIST-A', payment=payment, amount=Decimal('100'))
        b = ingest_chargeback(external_case_id='LIST-B', payment=payment, amount=Decimal('200'))
        accept_loss(b, note='')

        res = admin_client.get('/api/v1/payments/chargebacks/?status=accepted')
        assert res.status_code == 200
        cases = [r['external_case_id'] for r in res.data['results']]
        assert cases == ['LIST-B']

    def test_overdue_filter(self, admin_client, order_with_payment):
        _, payment = order_with_payment
        cb = ingest_chargeback(external_case_id='OD-1', payment=payment, amount=Decimal('100'))
        Chargeback.objects.filter(pk=cb.pk).update(
            deadline_at=timezone.now() - timedelta(days=2),
        )
        res = admin_client.get('/api/v1/payments/chargebacks/?overdue=1')
        ids = [r['external_case_id'] for r in res.data['results']]
        assert 'OD-1' in ids

    def test_detail_includes_evidence_packet(self, admin_client, order_with_payment):
        _, payment = order_with_payment
        cb = ingest_chargeback(external_case_id='DET-1', payment=payment, amount=Decimal('100'))
        res = admin_client.get(f'/api/v1/payments/chargebacks/{cb.pk}/')
        assert res.status_code == 200
        assert 'evidence_packet' in res.data

    def test_respond_endpoint(self, admin_client, order_with_payment):
        _, payment = order_with_payment
        cb = ingest_chargeback(external_case_id='RSP-1', payment=payment, amount=Decimal('100'))
        res = admin_client.post(
            f'/api/v1/payments/chargebacks/{cb.pk}/respond/',
            {'evidence': {'tracking': 'XYZ123'}},
            format='json',
        )
        assert res.status_code == 200
        assert res.data['status'] == 'evidence'

    def test_respond_invalid_state_returns_409(self, admin_client, order_with_payment, admin):
        _, payment = order_with_payment
        cb = ingest_chargeback(external_case_id='RSP-2', payment=payment, amount=Decimal('100'))
        accept_loss(cb, actor=admin)
        res = admin_client.post(
            f'/api/v1/payments/chargebacks/{cb.pk}/respond/',
            {'evidence': {}}, format='json',
        )
        assert res.status_code == 409

    def test_resolve_endpoint(self, admin_client, order_with_payment, admin):
        _, payment = order_with_payment
        cb = ingest_chargeback(external_case_id='RES-1', payment=payment, amount=Decimal('100'))
        submit_evidence(cb, evidence={'x': 1}, actor=admin)
        res = admin_client.post(
            f'/api/v1/payments/chargebacks/{cb.pk}/resolve/',
            {'won': True}, format='json',
        )
        assert res.status_code == 200
        assert res.data['status'] == 'won'


# ─── Inbound webhook (admin-auth path) ───────────────────────────────


@pytest.mark.django_db
class TestInboundWebhook:

    URL = '/api/v1/payments/chargebacks/inbound/'

    def test_admin_can_paste_chargeback(self, admin_client, order_with_payment):
        _, payment = order_with_payment
        res = admin_client.post(self.URL, {
            'external_case_id': 'WH-PASTE-1',
            'payment_id': payment.gateway_reference,
            'amount': '1000.00',
            'reason_code': 'fraud',
        }, format='json')
        assert res.status_code == 200
        assert res.data['external_case_id'] == 'WH-PASTE-1'

    def test_anonymous_rejected_without_hmac(self, api_client, order_with_payment):
        _, payment = order_with_payment
        res = api_client.post(self.URL, {
            'external_case_id': 'WH-ANON-1',
            'payment_id': payment.gateway_reference,
            'amount': '100',
        }, format='json')
        assert res.status_code == 401

    def test_missing_fields_400(self, admin_client):
        res = admin_client.post(self.URL, {'amount': '100'}, format='json')
        assert res.status_code == 400

    def test_unknown_payment_404(self, admin_client):
        res = admin_client.post(self.URL, {
            'external_case_id': 'WH-NOT-FOUND',
            'payment_id': 'does-not-exist',
            'amount': '100',
        }, format='json')
        assert res.status_code == 404

    def test_duplicate_idempotent(self, admin_client, order_with_payment):
        _, payment = order_with_payment
        a = admin_client.post(self.URL, {
            'external_case_id': 'WH-DUP',
            'payment_id': payment.gateway_reference,
            'amount': '500',
        }, format='json')
        b = admin_client.post(self.URL, {
            'external_case_id': 'WH-DUP',
            'payment_id': payment.gateway_reference,
            'amount': '500',
        }, format='json')
        assert a.status_code == 200
        assert b.status_code == 200
        assert a.data['id'] == b.data['id']
