from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class OrderAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_unauthenticated_order_list_rejected(self):
        response = self.client.get('/api/v1/orders/my/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_checkout_rejected(self):
        response = self.client.post('/api/v1/orders/checkout/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class OrderSoftDeleteTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(email='b@t.com', password='pass')
        self.seller = User.objects.create_user(email='s@t.com', password='pass')

    def test_hard_delete_raises(self):
        from apps.orders.models import Order
        import uuid
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            idempotency_key=str(uuid.uuid4()),
            subtotal='100.00',
            total='100.00',
        )
        with self.assertRaises(PermissionError):
            order.delete()

    def test_soft_delete_sets_flag(self):
        from apps.orders.models import Order
        import uuid
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            idempotency_key=str(uuid.uuid4()),
            subtotal='50.00',
            total='50.00',
        )
        order.soft_delete(deleted_by=self.buyer)
        order.refresh_from_db(using='default')
        from apps.orders.models import Order as O
        # Default manager excludes soft-deleted
        self.assertFalse(O.objects.filter(pk=order.pk).exists())
        # all_objects includes it
        self.assertTrue(O.all_objects.filter(pk=order.pk).exists())
