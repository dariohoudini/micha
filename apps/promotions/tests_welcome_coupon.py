"""
First-Run doc Screen 6 / CH7 — the welcome / first-order coupon.

A new account is born holding the BEMVINDO15 coupon so it's present at
the very first checkout (the new-user hook that survives having no
account until the gate). Locks: registration grants it, the grant is
idempotent, the welcome-offer endpoint surfaces it, and a pre-existing
user is back-filled.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.promotions.models import Coupon, UserCoupon
from apps.promotions.welcome import (
    WELCOME_CODE, ensure_welcome_coupon, grant_welcome_coupon,
)

User = get_user_model()


class WelcomeCouponTests(TestCase):

    def test_ensure_is_idempotent(self):
        c1 = ensure_welcome_coupon()
        c2 = ensure_welcome_coupon()
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(Coupon.objects.filter(code=WELCOME_CODE).count(), 1)
        self.assertEqual(c1.discount_type, 'percentage')
        self.assertEqual(c1.discount_value, 15)
        self.assertEqual(c1.usage_limit_per_user, 1)

    def test_grant_gives_available_usercoupon_once(self):
        u = User.objects.create_user(email='novo@test.ao',
                                     password='pw12345678!', username='novo')
        uc1 = grant_welcome_coupon(u)
        uc2 = grant_welcome_coupon(u)   # idempotent
        self.assertIsNotNone(uc1)
        self.assertEqual(uc1.pk, uc2.pk)
        self.assertEqual(uc1.status, 'available')
        self.assertEqual(
            UserCoupon.objects.filter(user=u, coupon__code=WELCOME_CODE).count(), 1)
        # a comfortable redemption window was set
        self.assertIsNotNone(uc1.coupon.valid_until)

    def test_registration_grants_the_welcome_coupon(self):
        client = APIClient()
        r = client.post('/api/v1/auth/register/', {
            'email': 'gatehitter@test.ao', 'username': 'gatehitter',
            'password': 'pw12345678!', 'password2': 'pw12345678!',
            'privacy_consent': True, 'terms_consent': True,
            'account_type': 'buyer',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(email='gatehitter@test.ao')
        self.assertTrue(UserCoupon.objects.filter(
            user=user, coupon__code=WELCOME_CODE, status='available').exists())

    def test_welcome_offer_endpoint_surfaces_the_coupon(self):
        u = User.objects.create_user(email='wo@test.ao',
                                     password='pw12345678!', username='wo')
        grant_welcome_coupon(u)
        client = APIClient()
        client.force_authenticate(u)
        r = client.get('/api/v1/promotions/welcome-offer/')
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data['offer'])
        self.assertEqual(r.data['offer']['code'], WELCOME_CODE)
        self.assertEqual(str(r.data['offer']['discount_value']), '15.00')
        self.assertEqual(r.data['offer']['status'], 'available')

    def test_welcome_offer_backfills_a_pre_existing_user(self):
        # A user who registered before the grant existed still gets it
        # the first time they open the welcome screen.
        u = User.objects.create_user(email='legacy@test.ao',
                                     password='pw12345678!', username='legacy')
        self.assertFalse(UserCoupon.objects.filter(user=u).exists())
        client = APIClient()
        client.force_authenticate(u)
        r = client.get('/api/v1/promotions/welcome-offer/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['offer']['code'], WELCOME_CODE)
        self.assertTrue(UserCoupon.objects.filter(
            user=u, coupon__code=WELCOME_CODE).exists())
