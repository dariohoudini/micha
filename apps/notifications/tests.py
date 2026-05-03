from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class NotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='n@t.com', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_list_empty_for_new_user(self):
        response = self.client.get('/api/v1/notifications/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unread_count_starts_at_zero(self):
        response = self.client.get('/api/v1/notifications/unread-count/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_count'], 0)

    def test_send_creates_notification(self):
        from apps.notifications.models import Notification
        n = Notification.send(
            user=self.user,
            type='system',
            title='Test',
            message='Hello',
            reference_id='test-001',
        )
        self.assertIsNotNone(n)
        self.assertEqual(n.type, 'system')
        self.assertFalse(n.is_read)

    def test_deduplication_prevents_duplicate(self):
        from apps.notifications.models import Notification
        Notification.send(user=self.user, type='order', title='T', message='M', reference_id='ord-1')
        second = Notification.send(user=self.user, type='order', title='T', message='M', reference_id='ord-1')
        self.assertIsNone(second)
        self.assertEqual(Notification.objects.filter(user=self.user, reference_id='ord-1').count(), 1)

    def test_mark_read(self):
        from apps.notifications.models import Notification
        n = Notification.send(user=self.user, type='system', title='T', message='M')
        response = self.client.patch(f'/api/v1/notifications/{n.pk}/read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/notifications/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
