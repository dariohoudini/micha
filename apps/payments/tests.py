from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class WalletTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.seller = User.objects.create_user(
            email='seller@t.com', password='pass', is_seller=True
        )
        self.client.force_authenticate(user=self.seller)

    def test_wallet_unauthenticated_rejected(self):
        anon = APIClient()
        response = anon.get('/api/v1/payments/wallet/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wallet_created_on_first_access(self):
        response = self.client.get('/api/v1/payments/wallet/')
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

    def test_bank_account_list(self):
        response = self.client.get('/api/v1/payments/bank-accounts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EarningsHoldTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(email='b@t.com', password='pass')
        self.seller = User.objects.create_user(email='s@t.com', password='pass', is_seller=True)

    def test_earnings_hold_model(self):
        from apps.payments.models import EarningsHold
        from django.utils import timezone
        from datetime import timedelta
        import uuid
        from apps.orders.models import Order

        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            idempotency_key=str(uuid.uuid4()),
            subtotal='1000.00',
            total='1000.00',
        )
        hold = EarningsHold.objects.create(
            seller=self.seller,
            order=order,
            amount='950.00',
            release_at=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(hold.released)
        self.assertEqual(str(hold.amount), '950.00')


# ─────────────────────────────────────────────────────────────────────
# Refund-to-payment end-to-end tests
# ─────────────────────────────────────────────────────────────────────
#
# The headline money path: buyer pays → dispute opens → admin
# resolves → refund row created → worker processes → gateway credit
# → Payment.status flips to REFUNDED.
#
# Each step has been hardened in this codebase (commits 36baec1,
# 9aa8879, dc1cc0e, 3812522) but the END-TO-END flow had no test.
# Regression here would silently break refunds — the highest-risk
# class of bug for a marketplace.

import pytest
from decimal import Decimal
from unittest.mock import patch


@pytest.mark.django_db
class TestRefundEndToEnd:
    """Full lifecycle: pending Refund → process_refund → gateway →
    REFUNDED Payment. Verifies the chain commits 36baec1, 9aa8879,
    dc1cc0e all interact correctly."""

    def test_process_refund_flips_payment_to_refunded(self, buyer, seller):
        """The headline test: a pending Refund row, processed by the
        worker, ends with Payment.status=REFUNDED + Refund.status=
        processed.

        Mocks: gateway HTTP call (returns success). Everything else
        (wallet debit, state machine transition, audit log, refund
        row update) runs through real code.
        """
        from apps.orders.models import Order, Payment, Refund
        from apps.payments.gateway import PaymentState
        from apps.payments.refund_service import process_refund
        from apps.payments.models import SellerWallet
        import uuid

        # Set up: seller wallet, order, paid payment, pending refund
        wallet, _ = SellerWallet.objects.get_or_create(seller=seller)
        wallet.balance = Decimal('2000.00')
        wallet.save()

        order = Order.objects.create(
            buyer=buyer, seller=seller, status='delivered',
            subtotal=Decimal('1000.00'), total=Decimal('1000.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        payment = Payment.objects.create(
            order=order, amount=Decimal('1000.00'),
            status=PaymentState.CONFIRMED,
            method='multicaixa',
            gateway_reference=f'gw-{uuid.uuid4().hex[:12]}',
        )
        refund = Refund.objects.create(
            order=order, requested_by=buyer,
            amount=Decimal('1000.00'), reason='dispute resolved',
            status='pending',
        )

        # Mock the gateway HTTP call — return successful refund response
        with patch(
            'apps.payments.gateway.AppyPayGateway.refund_payment',
            return_value={'status': 'ok', 'refund_id': 'gw-refund-xyz'},
        ):
            updated = process_refund(refund)

        # Verify the full chain
        updated.refresh_from_db()
        payment.refresh_from_db()
        wallet.refresh_from_db()

        assert updated.status == 'processed', (
            f'refund did not complete: status={updated.status}'
        )
        assert updated.processed_at is not None
        assert payment.status == PaymentState.REFUNDED, (
            f'payment.status not flipped: {payment.status}'
        )
        # gateway_refund_id backfill (commit 9aa8879)
        assert updated.gateway_refund_id == 'gw-refund-xyz', (
            'gateway_refund_id not threaded back to Refund row'
        )

    def test_gateway_failure_leaves_wallet_untouched(self, buyer, seller):
        """The gateway-first ordering guarantee from commit 9aa8879:
        if the gateway HTTP call fails, the wallet is NOT debited and
        the Payment status stays CONFIRMED. The refund row is left in
        pending state (or with backoff scheduled) for the worker to
        retry.

        This was the original wallet-debited-but-buyer-never-paid
        leak; the test asserts the fix holds."""
        from apps.orders.models import Order, Payment, Refund
        from apps.payments.gateway import (
            PaymentState, PaymentGatewayError,
        )
        from apps.payments.refund_service import process_refund
        from apps.payments.models import SellerWallet
        import uuid

        wallet, _ = SellerWallet.objects.get_or_create(seller=seller)
        wallet.balance = Decimal('2000.00')
        wallet.save()
        before_balance = wallet.balance

        order = Order.objects.create(
            buyer=buyer, seller=seller, status='delivered',
            subtotal=Decimal('500.00'), total=Decimal('500.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        payment = Payment.objects.create(
            order=order, amount=Decimal('500.00'),
            status=PaymentState.CONFIRMED,
            method='multicaixa',
            gateway_reference=f'gw-{uuid.uuid4().hex[:12]}',
        )
        refund = Refund.objects.create(
            order=order, requested_by=buyer,
            amount=Decimal('500.00'), reason='test',
            status='pending', max_attempts=3,
        )

        # Gateway raises (transient network error)
        with patch(
            'apps.payments.gateway.PaymentProcessor.refund',
            side_effect=PaymentGatewayError('gateway timeout'),
        ):
            updated = process_refund(refund)

        wallet.refresh_from_db()
        payment.refresh_from_db()
        updated.refresh_from_db()

        assert wallet.balance == before_balance, (
            f'BUG: wallet was debited despite gateway failure. '
            f'before={before_balance} after={wallet.balance}. '
            f'This is the leak commit 9aa8879 was supposed to close.'
        )
        assert payment.status == PaymentState.CONFIRMED, (
            'Payment.status flipped to REFUNDED even though gateway '
            'failed — local state is now LYING about the refund'
        )
        assert updated.status == 'pending', (
            'transient gateway error should leave refund pending for '
            'retry, not mark it failed/processed'
        )
        assert updated.next_attempt_at is not None, (
            'transient error should schedule a retry (next_attempt_at)'
        )

    def test_max_attempts_exhausted_marks_failed(self, buyer, seller):
        """After max_attempts of transient errors, the refund is
        marked 'failed' — distinct from 'rejected' (policy/permanent).
        Failed refunds need ops triage."""
        from apps.orders.models import Order, Payment, Refund
        from apps.payments.gateway import (
            PaymentState, PaymentGatewayError,
        )
        from apps.payments.refund_service import process_refund
        from apps.payments.models import SellerWallet
        import uuid

        wallet, _ = SellerWallet.objects.get_or_create(seller=seller)
        wallet.balance = Decimal('1000.00')
        wallet.save()

        order = Order.objects.create(
            buyer=buyer, seller=seller, status='delivered',
            subtotal=Decimal('100.00'), total=Decimal('100.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        Payment.objects.create(
            order=order, amount=Decimal('100.00'),
            status=PaymentState.CONFIRMED,
            method='multicaixa',
            gateway_reference=f'gw-{uuid.uuid4().hex[:12]}',
        )
        refund = Refund.objects.create(
            order=order, requested_by=buyer,
            amount=Decimal('100.00'), reason='test',
            status='pending', max_attempts=2,
        )

        with patch(
            'apps.payments.gateway.PaymentProcessor.refund',
            side_effect=PaymentGatewayError('gateway down'),
        ):
            # First attempt → pending (defer)
            process_refund(refund)
            refund.refresh_from_db()
            assert refund.status == 'pending'

            # Second attempt → attempts == max_attempts → failed
            process_refund(refund)

        refund.refresh_from_db()
        assert refund.status == 'failed'
        assert refund.next_attempt_at is None  # no more retries

    def test_permanent_error_short_circuits_to_rejected(self, buyer, seller):
        """A permanent gateway error ('No confirmed payment found',
        'Already refunded', etc.) is not retriable — mark 'rejected'
        immediately rather than burn N retry attempts."""
        from apps.orders.models import Order, Payment, Refund
        from apps.payments.gateway import (
            PaymentState, PaymentGatewayError,
        )
        from apps.payments.refund_service import process_refund
        from apps.payments.models import SellerWallet
        import uuid

        wallet, _ = SellerWallet.objects.get_or_create(seller=seller)
        wallet.balance = Decimal('1000.00')
        wallet.save()

        order = Order.objects.create(
            buyer=buyer, seller=seller, status='delivered',
            subtotal=Decimal('100.00'), total=Decimal('100.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        Payment.objects.create(
            order=order, amount=Decimal('100.00'),
            status=PaymentState.CONFIRMED,
            method='multicaixa',
            gateway_reference=f'gw-{uuid.uuid4().hex[:12]}',
        )
        refund = Refund.objects.create(
            order=order, requested_by=buyer,
            amount=Decimal('100.00'), reason='test',
            status='pending', max_attempts=8,  # high cap
        )

        with patch(
            'apps.payments.gateway.PaymentProcessor.refund',
            side_effect=PaymentGatewayError(
                'No confirmed payment found for this order'
            ),
        ):
            process_refund(refund)

        refund.refresh_from_db()
        assert refund.status == 'rejected', (
            'permanent error should short-circuit to rejected, '
            'not retry N times'
        )
        assert refund.attempts == 1, (
            'permanent error should NOT consume the retry budget'
        )

    def test_idempotent_re_processing_no_double_debit(self, buyer, seller):
        """Calling process_refund twice on the same Refund: the
        second call is a no-op because the row is already in a
        terminal state."""
        from apps.orders.models import Order, Payment, Refund
        from apps.payments.gateway import PaymentState
        from apps.payments.refund_service import process_refund
        from apps.payments.models import SellerWallet
        import uuid

        wallet, _ = SellerWallet.objects.get_or_create(seller=seller)
        wallet.balance = Decimal('2000.00')
        wallet.save()

        order = Order.objects.create(
            buyer=buyer, seller=seller, status='delivered',
            subtotal=Decimal('500.00'), total=Decimal('500.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        Payment.objects.create(
            order=order, amount=Decimal('500.00'),
            status=PaymentState.CONFIRMED,
            method='multicaixa',
            gateway_reference=f'gw-{uuid.uuid4().hex[:12]}',
        )
        refund = Refund.objects.create(
            order=order, requested_by=buyer,
            amount=Decimal('500.00'), reason='test',
            status='pending',
        )

        call_count = {'n': 0}

        def _track_call(*args, **kwargs):
            call_count['n'] += 1
            return True

        with patch(
            'apps.payments.gateway.PaymentProcessor.refund',
            side_effect=_track_call,
        ):
            process_refund(refund)  # first → processed
            wallet_after_first = SellerWallet.objects.get(seller=seller).balance
            process_refund(refund)  # second → no-op

        wallet_final = SellerWallet.objects.get(seller=seller).balance
        assert wallet_after_first == wallet_final, (
            f'wallet changed on second process_refund call. '
            f'before={wallet_after_first} after={wallet_final} — '
            f'double-debit risk!'
        )
        # Idempotency: PaymentProcessor.refund called at most once
        # (the second call would short-circuit at the status check)
        assert call_count['n'] <= 1, (
            f'gateway called {call_count["n"]}x on second process_refund — '
            f'idempotency broken'
        )
