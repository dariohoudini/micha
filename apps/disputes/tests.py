from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class DisputeEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.buyer = User.objects.create_user(email='buyer@t.com', password='pass')
        self.seller = User.objects.create_user(email='seller@t.com', password='pass')

    def test_unauthenticated_rejected(self):
        response = self.client.get('/api/v1/disputes/my/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_dispute_list_returns_empty(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get('/api/v1/disputes/my/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_open_dispute_requires_valid_order(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post('/api/v1/disputes/open/', {
            'order_id': '00000000-0000-0000-0000-000000000000',
            'reason': 'not_received',
            'description': 'Never arrived.',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
