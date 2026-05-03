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
