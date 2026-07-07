"""
Gap-Coverage CH16/CH17 — the #1 money gap: money-out demands a fresh
second factor. Locks: a session/password alone can NEVER request a
payout or change a bank account; an enrolled second factor (fresh TOTP
or a live step-up window) is required; and the window is single-use.
"""
import pyotp
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.users.stepup import grant_stepup, has_stepup

User = get_user_model()
SECRET = pyotp.random_base32()


class MoneyOutStepUpTests(TestCase):

    def setUp(self):
        cache.clear()
        self.seller = User.objects.create_user(
            email='s@test.ao', password='pw12345678!', username='s',
            is_seller=True, is_verified_seller=True)
        self.client = APIClient()
        self.client.force_authenticate(self.seller)

    def _enable_2fa(self):
        self.seller.two_fa_enabled = True
        self.seller.two_fa_secret = SECRET
        self.seller.save(update_fields=['two_fa_enabled', 'two_fa_secret'])

    def _code(self):
        return pyotp.TOTP(SECRET).now()

    def _payout(self, **headers):
        return self.client.post(
            '/api/v1/payments/payout/request/',
            {'amount': '1000', 'bank_account_id': 1},
            format='json',
            HTTP_IDEMPOTENCY_KEY='po-test-1', **headers)

    # ── the hole: no 2FA → money-out blocked (was allowed on session) ──
    def test_payout_blocked_without_2fa_enrolled(self):
        r = self._payout()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'mfa_required_for_payout')

    def test_step_up_endpoint_requires_2fa(self):
        r = self.client.post('/api/v1/auth/step-up/',
                             {'totp_code': '000000'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'mfa_required_for_payout')

    def test_payout_blocked_with_2fa_but_no_stepup(self):
        self._enable_2fa()
        r = self._payout()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'stepup_required')

    def test_wrong_totp_rejected(self):
        self._enable_2fa()
        r = self._payout(HTTP_X_TOTP_CODE='000000')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'invalid_2fa')

    STEPUP_ERRORS = {'mfa_required_for_payout', 'stepup_required', 'invalid_2fa'}

    def test_fresh_totp_authorises_and_passes_the_gate(self):
        self._enable_2fa()
        # A fresh code passes the step-up gate; the request proceeds past
        # the money-out check into the payout logic (which legitimately
        # 4xx's on the fake bank id / KYC tier — but NOT with a step-up
        # rejection, which is what we're locking).
        r = self._payout(HTTP_X_TOTP_CODE=self._code())
        self.assertNotIn(r.data.get('error'), self.STEPUP_ERRORS)

    def test_step_up_endpoint_opens_window_then_payout_passes(self):
        self._enable_2fa()
        s = self.client.post('/api/v1/auth/step-up/',
                             {'totp_code': self._code()}, format='json')
        self.assertEqual(s.status_code, 200)
        self.assertEqual(s.data['status'], 'stepped_up')
        self.assertTrue(has_stepup(self.seller.id))
        # a subsequent payout within the window is authorised (any later
        # 4xx is downstream business logic, not a step-up rejection)
        r = self._payout()
        self.assertNotIn(r.data.get('error'), self.STEPUP_ERRORS)

    def test_window_is_single_use(self):
        self._enable_2fa()
        grant_stepup(self.seller.id, 'money_out')
        self.assertTrue(has_stepup(self.seller.id))
        self._payout()                       # consumes the window
        self.assertFalse(has_stepup(self.seller.id))
        # the very next payout with no fresh factor is blocked again
        r = self._payout()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'stepup_required')

    def test_bank_add_also_gated(self):
        r = self.client.post('/api/v1/payments/bank-accounts/',
                             {'bank_name': 'BAI', 'account_name': 'S',
                              'account_number': '123', 'iban': 'AO06'},
                             format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'mfa_required_for_payout')
