"""
Gap-Coverage CH10 — refresh-token reuse detection + family revocation.

Rotation + blacklist make each refresh token single-use. These tests
PROVE the containment the IAM/Security spec requires: presenting an
already-rotated refresh token (a stolen replay) revokes the user's
ENTIRE outstanding-token family, logging out thief and victim both.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

REFRESH_URL = '/api/v1/auth/token/refresh/'


class TokenReuseFamilyRevocationTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='reuse@test.ao', password='pw12345678!', username='reuse')
        self.client = APIClient()

    def _refresh(self, token):
        return self.client.post(REFRESH_URL, {'refresh': token},
                                format='json')

    def test_normal_rotation_works(self):
        t0 = str(RefreshToken.for_user(self.user))
        r = self._refresh(t0)
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)
        self.assertIn('refresh', r.data)
        self.assertNotEqual(r.data['refresh'], t0)

    def test_reuse_of_rotated_token_revokes_the_family(self):
        t0 = str(RefreshToken.for_user(self.user))
        r1 = self._refresh(t0)
        self.assertEqual(r1.status_code, 200)
        t1 = r1.data['refresh']

        # Replay the OLD (rotated) token — the theft signal.
        replay = self._refresh(t0)
        self.assertEqual(replay.status_code, 401)

        # Containment: the CURRENT token (t1, held by whoever) must now be
        # dead too — the whole family was revoked, forcing re-auth.
        r2 = self._refresh(t1)
        self.assertEqual(r2.status_code, 401)

    def test_unrelated_session_of_same_user_is_also_revoked(self):
        # The family is per-user across outstanding tokens: a stolen-token
        # replay is an account-compromise signal, so ALL sessions die.
        t_phone = str(RefreshToken.for_user(self.user))
        t_web = str(RefreshToken.for_user(self.user))
        r = self._refresh(t_phone)
        self.assertEqual(r.status_code, 200)
        self._refresh(t_phone)                      # replay → containment
        self.assertEqual(self._refresh(t_web).status_code, 401)

    def test_garbage_token_does_not_nuke_valid_sessions(self):
        # A forged/garbage refresh is a plain 401 — NOT a reuse signal; it
        # must not let an attacker DoS a victim by spraying junk.
        t0 = str(RefreshToken.for_user(self.user))
        r = self._refresh('garbage.token.value')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self._refresh(t0).status_code, 200)
