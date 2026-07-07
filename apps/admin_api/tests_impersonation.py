"""
Admin User Management doc CH17 — impersonation / view-as.

Locks: an operator mints a time-boxed token to act AS a user, it is
recorded on both sides, staff can't be impersonated, and the dangerous
actions (money-out, password, 2FA, delete) are BLOCKED even with the
impersonation token.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.admin_actions.models import AdminActionLog
from apps.users.impersonation import IMPERSONATION_MINUTES

User = get_user_model()


class ImpersonationTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email='op@micha.ao', password='pw12345678!', username='op',
            is_staff=True)
        self.target = User.objects.create_user(
            email='u@test.ao', password='pw12345678!', username='u',
            is_seller=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f'/api/v1/admin-api/users/{self.target.id}/impersonate/'

    def test_non_staff_cannot_impersonate(self):
        c = APIClient()
        c.force_authenticate(self.target)
        self.assertEqual(c.post(self.url).status_code, 403)

    def test_issues_token_and_audits_both_sides(self):
        r = self.client.post(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)
        self.assertEqual(r.data['acting_as']['email'], 'u@test.ao')
        self.assertEqual(r.data['expires_in_minutes'], IMPERSONATION_MINUTES)
        # audited to the real operator
        self.assertTrue(AdminActionLog.objects.filter(
            action='user.impersonated', admin=self.admin,
            target_id=str(self.target.id)).exists())
        # recorded on the target's own timeline
        from apps.users.models import UserActivityLog
        self.assertTrue(UserActivityLog.objects.filter(
            user=self.target, action='impersonation_started').exists())

    def test_cannot_impersonate_staff(self):
        other_op = User.objects.create_user(
            email='op2@micha.ao', password='pw12345678!', username='op2',
            is_staff=True)
        r = self.client.post(
            f'/api/v1/admin-api/users/{other_op.id}/impersonate/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'cannot_impersonate_staff')

    def _impersonated_client(self):
        token = self.client.post(self.url).data['access']
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return c

    def test_dangerous_actions_blocked_under_impersonation(self):
        c = self._impersonated_client()
        # password change → blocked by NotImpersonated permission
        r = c.post('/api/v1/auth/change-password/',
                   {'old_password': 'x', 'new_password': 'y'}, format='json')
        self.assertEqual(r.status_code, 403)
        # account deletion → blocked
        r = c.post('/api/v1/auth/delete-account/', {}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_money_out_blocked_under_impersonation(self):
        # even with the target's session, the impersonator can't withdraw
        self.target.is_verified_seller = True
        self.target.save(update_fields=['is_verified_seller'])
        c = self._impersonated_client()
        r = c.post('/api/v1/payments/payout/request/',
                   {'amount': '1000', 'bank_account_id': 1}, format='json',
                   HTTP_IDEMPOTENCY_KEY='imp-po-1')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'blocked_under_impersonation')

    def test_ordinary_read_works_under_impersonation(self):
        # view-as: the operator CAN see the platform as the user
        c = self._impersonated_client()
        r = c.get('/api/v1/auth/profile/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['email'], 'u@test.ao')
