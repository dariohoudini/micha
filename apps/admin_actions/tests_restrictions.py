"""
Admin User Management doc CH5 — graduated RESTRICT enforcement.

Locks: an operator can restrict specific capabilities (sell / withdraw /
message) short of a full suspend, with a required reason; the
restriction is enforced at each capability's endpoint; the inspector
reflects it; and un-restrict lifts it.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.admin_actions.models import UserRestriction

User = get_user_model()


class RestrictionModelTests(TestCase):
    def test_is_restricted_helper(self):
        u = User.objects.create_user(email='u@test.ao', password='pw12345678!',
                                     username='u')
        self.assertFalse(u.is_restricted('withdrawal'))
        UserRestriction.objects.create(user=u, no_withdrawal=True,
                                       reason='fraude em investigação')
        self.assertTrue(u.is_restricted('withdrawal'))
        self.assertFalse(u.is_restricted('selling'))
        # lifting it clears the helper
        u.restriction.is_active = False
        u.restriction.save()
        u.refresh_from_db()
        self.assertFalse(u.is_restricted('withdrawal'))


class AdminRestrictActionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='op@micha.ao', password='pw12345678!', username='op',
            is_staff=True)
        self.target = User.objects.create_user(
            email='t@test.ao', password='pw12345678!', username='t',
            is_seller=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f'/api/v1/admin-api/users/{self.target.id}/action/'

    def test_restrict_requires_reason(self):
        r = self.client.post(self.url, {'action': 'restrict',
                                        'no_selling': True}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['error'], 'reason_required')

    def test_restrict_and_unrestrict(self):
        r = self.client.post(self.url, {
            'action': 'restrict', 'no_selling': True, 'no_messaging': True,
            'reason': 'anúncios suspeitos',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['no_selling'])
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_restricted('selling'))
        self.assertTrue(self.target.is_restricted('messaging'))
        self.assertFalse(self.target.is_restricted('withdrawal'))
        # un-restrict lifts everything
        r2 = self.client.post(self.url, {'action': 'unrestrict'}, format='json')
        self.assertEqual(r2.data['status'], 'unrestricted')
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_restricted('selling'))

    def test_restriction_shows_in_inspector(self):
        self.client.post(self.url, {'action': 'restrict', 'no_withdrawal': True,
                                    'reason': 'x'}, format='json')
        insp = self.client.get(
            f'/api/v1/admin-api/users/{self.target.id}/inspector/')
        self.assertTrue(insp.data['access']['restriction']['withdrawal'])
        self.assertFalse(insp.data['access']['can_withdraw']['enabled'])
        self.assertIn('restrito', insp.data['access']['can_withdraw']['reason'])


class RestrictionEnforcementTests(TestCase):
    def setUp(self):
        from apps.stores.models import Store
        self.seller = User.objects.create_user(
            email='seller@test.ao', password='pw12345678!', username='seller',
            is_seller=True, is_verified_seller=True)
        self.store = Store.objects.create(owner=self.seller, name='Loja')
        self.client = APIClient()
        self.client.force_authenticate(self.seller)

    def _restrict(self, **flags):
        UserRestriction.objects.update_or_create(
            user=self.seller,
            defaults={'reason': 'test', 'is_active': True, **flags})

    def test_selling_restriction_blocks_product_create(self):
        self._restrict(no_selling=True)
        r = self.client.post('/api/v1/products/create/',
                             {'title': 'Item', 'price': '1000',
                              'category': 1, 'quantity': 5, 'tags': ''},
                             format='json',
                             HTTP_IDEMPOTENCY_KEY='pc-restrict-1')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'restricted')

    def test_messaging_restriction_blocks_new_chat(self):
        other = User.objects.create_user(
            email='o@test.ao', password='pw12345678!', username='o',
            is_seller=True)
        self._restrict(no_messaging=True)
        r = self.client.post('/api/v1/chat/conversations/',
                             {'seller_id': other.id}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'restricted')
