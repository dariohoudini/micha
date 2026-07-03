"""
Admin User Management doc — the inspector panel + security actions.

Locks the slice: the inspector assembles the account truth in one
authorized read AND that read is itself audited (the watchers are
watched); terminate-sessions forces re-auth NOW (sessions dead + token
family revoked); suspend does the same (CH5: logged out now, not
"cannot log in again"); password reset is a user-completed flow the
operator only triggers.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.admin_actions.models import AdminActionLog
from apps.users.models import UserActivityLog, UserSession

User = get_user_model()


class UserInspectorTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email='op@micha.ao', password='pw12345678!', username='op',
            is_staff=True)
        self.target = User.objects.create_user(
            email='alvo@test.ao', password='pw12345678!', username='alvo',
            is_phone_verified=True)
        UserSession.objects.create(user=self.target, ip_address='10.0.0.9',
                                   device='iPhone 13')
        UserActivityLog.objects.create(user=self.target, action='login',
                                       ip_address='10.0.0.9',
                                       device='iPhone 13')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f'/api/v1/admin-api/users/{self.target.id}/inspector/'

    def test_non_staff_denied(self):
        buyer_client = APIClient()
        buyer_client.force_authenticate(self.target)
        self.assertEqual(buyer_client.get(self.url).status_code, 403)

    def test_inspector_assembles_the_panel(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        for section in ('identity', 'verification_ladder', 'security',
                        'last_sign_ons', 'sessions', 'devices', 'risk',
                        'access', 'history'):
            self.assertIn(section, r.data)
        self.assertEqual(r.data['identity']['lifecycle'], 'active')
        self.assertEqual(r.data['verification_ladder']['level'], 1)
        self.assertEqual(len(r.data['sessions']), 1)
        self.assertGreaterEqual(r.data['sessions'][0]['duration_seconds'], 0)
        self.assertEqual(r.data['last_sign_ons'][0]['ip'], '10.0.0.9')
        # access gates are explained
        self.assertFalse(r.data['access']['can_withdraw']['enabled'])
        self.assertIn('KYC', r.data['access']['can_withdraw']['reason'])

    def test_opening_a_user_is_itself_audited(self):
        # The watchers are watched (doc CH12): the READ writes a
        # non-repudiation row attributing the PII access to the operator.
        self.client.get(self.url)
        row = AdminActionLog.objects.filter(
            action='user.inspector_viewed', target_type='user',
            target_id=str(self.target.id)).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.admin, self.admin)

    def test_never_exposes_secrets(self):
        r = self.client.get(self.url)
        body = str(r.data)
        self.assertNotIn(self.target.password, body)   # Argon2 hash
        for forbidden in ('password_hash', 'two_fa_secret', 'otp_hash'):
            self.assertNotIn(forbidden, body)

    def test_terminate_sessions_forces_reauth_now(self):
        refresh = str(RefreshToken.for_user(self.target))
        r = self.client.post(
            f'/api/v1/admin-api/users/{self.target.id}/sessions/terminate/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['sessions_terminated'], 1)
        self.assertGreaterEqual(r.data['tokens_revoked'], 1)
        # session registry dead
        self.assertFalse(UserSession.objects.filter(
            user=self.target, is_active=True).exists())
        # refresh token family dead → the user must re-authenticate
        anon = APIClient()
        rr = anon.post('/api/v1/auth/token/refresh/', {'refresh': refresh},
                       format='json')
        self.assertEqual(rr.status_code, 401)
        # audited
        self.assertTrue(AdminActionLog.objects.filter(
            action='user.sessions_terminated',
            target_id=str(self.target.id)).exists())

    def test_suspend_terminates_sessions_immediately(self):
        # Doc CH5: suspension = logged out NOW.
        refresh = str(RefreshToken.for_user(self.target))
        r = self.client.post(
            f'/api/v1/admin-api/users/{self.target.id}/action/',
            {'action': 'suspend'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(UserSession.objects.filter(
            user=self.target, is_active=True).exists())
        anon = APIClient()
        rr = anon.post('/api/v1/auth/token/refresh/', {'refresh': refresh},
                       format='json')
        self.assertEqual(rr.status_code, 401)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        # inspector reflects the lifecycle
        insp = self.client.get(self.url)
        self.assertEqual(insp.data['identity']['lifecycle'], 'suspended')

    def test_password_reset_is_user_completed(self):
        r = self.client.post(
            f'/api/v1/admin-api/users/{self.target.id}/password-reset/')
        self.assertEqual(r.status_code, 200)
        # The OTP hash landed on the user (the flow is live) but the
        # response never contains the code — the operator can't learn it.
        self.target.refresh_from_db()
        body = str(r.data)
        self.assertNotIn('otp', body.lower().replace('_', ''))
        self.assertTrue(AdminActionLog.objects.filter(
            action='user.password_reset_triggered',
            target_id=str(self.target.id)).exists())
