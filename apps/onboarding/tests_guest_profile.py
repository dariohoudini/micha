"""
First-Run doc CH10/CH11 — the guest profile + carry-over.

Locks: a device-keyed PII-free guest profile is created and patched
without an account (region/language/interests/permissions), onboarding
completes/skips, and at signup the profile carries onto the new user
(language + interests) idempotently.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.onboarding.models import GuestProfile
from apps.onboarding.services import carry_over_guest_profile

User = get_user_model()
DEV = 'device-abc-123'


class GuestProfileApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()   # no auth — guest endpoints are AllowAny

    def test_session_creates_profile_with_angola_defaults(self):
        r = self.client.post('/api/v1/guest/session/',
                             {'device_id': DEV,
                              'attribution': {'source': 'organic'}},
                             format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data['new_guest'])
        self.assertEqual(r.data['guest']['locale']['currency'], 'AOA')
        self.assertEqual(r.data['guest']['locale']['language'], 'pt-AO')
        # idempotent: a second session returns the same profile
        r2 = self.client.post('/api/v1/guest/session/',
                              {'device_id': DEV}, format='json')
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.data['new_guest'])
        self.assertEqual(GuestProfile.objects.filter(device_id=DEV).count(), 1)

    def test_patch_writes_locale_and_interests_no_account(self):
        self.client.post('/api/v1/guest/session/', {'device_id': DEV},
                         format='json')
        r = self.client.patch('/api/v1/guest/profile/', {
            'device_id': DEV,
            'locale': {'language': 'en'},
            'interests': [1, 2, 2, 3],   # de-duped
            'permissions': {'notif': 'granted'},
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['locale']['language'], 'en')
        self.assertEqual(r.data['locale']['currency'], 'AOA')  # kept
        self.assertEqual(r.data['interests'], [1, 2, 3])
        self.assertEqual(r.data['onboarding_status'], 'in_progress')

    def test_complete_and_skip(self):
        self.client.post('/api/v1/guest/session/', {'device_id': DEV},
                         format='json')
        r = self.client.post('/api/v1/onboarding/complete/',
                             {'device_id': DEV}, format='json')
        self.assertEqual(r.data['onboarding_status'], 'completed')
        self.assertIsNotNone(r.data['completed_at'])
        r2 = self.client.post('/api/v1/onboarding/complete/',
                              {'device_id': 'dev-skip', 'skipped': True},
                              format='json')
        self.assertEqual(r2.data['onboarding_status'], 'skipped')

    def test_interests_grid_is_public(self):
        r = self.client.get('/api/v1/onboarding/interests/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('interests', r.data)

    def test_profile_requires_device_id(self):
        self.assertEqual(
            self.client.post('/api/v1/guest/session/', {}, format='json').status_code, 400)
        self.assertEqual(
            self.client.get('/api/v1/guest/profile/').status_code, 404)


class CarryOverTests(TestCase):

    def test_carry_over_copies_locale_and_links(self):
        GuestProfile.objects.create(
            device_id=DEV,
            locale={'language': 'pt-AO', 'currency': 'AOA'},
            interests=[1, 2])
        user = User.objects.create_user(email='c@test.ao',
                                        password='pw12345678!', username='c')
        gp = carry_over_guest_profile(user, DEV)
        user.refresh_from_db()
        self.assertEqual(user.language, 'pt')       # pt-AO → pt
        self.assertEqual(gp.linked_user_id, user.id)
        self.assertIsNotNone(gp.carried_over_at)

    def test_carry_over_is_idempotent(self):
        GuestProfile.objects.create(device_id=DEV,
                                    locale={'language': 'en'})
        user = User.objects.create_user(email='c2@test.ao',
                                        password='pw12345678!', username='c2')
        carry_over_guest_profile(user, DEV)
        # a second call is a no-op (already linked)
        gp = carry_over_guest_profile(user, DEV)
        self.assertEqual(gp.linked_user_id, user.id)

    def test_unknown_device_is_safe_noop(self):
        user = User.objects.create_user(email='c3@test.ao',
                                        password='pw12345678!', username='c3')
        self.assertIsNone(carry_over_guest_profile(user, 'nope'))
        self.assertIsNone(carry_over_guest_profile(user, ''))

    def test_registration_with_device_id_carries_over(self):
        GuestProfile.objects.create(
            device_id=DEV, locale={'language': 'pt-AO', 'currency': 'AOA'})
        client = APIClient()
        r = client.post('/api/v1/auth/register/', {
            'email': 'reg@test.ao', 'username': 'reg',
            'password': 'pw12345678!', 'password2': 'pw12345678!',
            'privacy_consent': True, 'terms_consent': True,
            'device_id': DEV, 'account_type': 'buyer',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(email='reg@test.ao')
        self.assertEqual(user.language, 'pt')
        self.assertTrue(GuestProfile.objects.get(device_id=DEV).linked_user_id == user.id)
