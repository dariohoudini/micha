"""
Guest-First doc CH12 — cart-merge conflict surfacing.

The guest cart (client-side, localStorage) folds into the user's server
cart on login via /cart/merge/. The doc's signature requirement: NEVER
silently drop, cap, or re-price — surface every conflict (removed /
price_changed / stock_capped) so the user sees what changed before
checkout. These tests lock that behaviour.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cart.models import Cart, CartItem
from apps.products.models import Product
from apps.stores.models import Store

User = get_user_model()


class CartMergeConflictTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='guest@test.ao', password='pw12345678!', username='guest')
        self.seller = User.objects.create_user(
            email='vend@test.ao', password='pw12345678!', username='vend',
            is_seller=True)
        self.store = Store.objects.create(owner=self.seller, name='Loja')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _product(self, price='1000.00', qty=10, active=True):
        return Product.objects.create(
            store=self.store, title='Produto', description='x',
            price=Decimal(price), quantity=qty, is_active=active,
        )

    def _merge(self, items):
        return self.client.post('/api/v1/cart/merge/', {'items': items},
                                format='json')

    def test_clean_merge_has_no_conflicts(self):
        p = self._product()
        r = self._merge([{'product_id': p.id, 'quantity': 2,
                          'price_at_add': '1000.00'}])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['merged'], 1)
        self.assertEqual(r.data['conflicts'], [])
        self.assertEqual(
            CartItem.objects.get(cart__user=self.user, product=p).quantity, 2)

    def test_removed_product_is_surfaced_not_silently_dropped(self):
        p = self._product(active=False)
        r = self._merge([{'product_id': p.id, 'quantity': 1}])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['merged'], 0)
        kinds = [c['kind'] for c in r.data['conflicts']]
        self.assertIn('removed', kinds)

    def test_out_of_stock_is_surfaced_as_removed(self):
        p = self._product(qty=0)
        r = self._merge([{'product_id': p.id, 'quantity': 1}])
        self.assertEqual([c['kind'] for c in r.data['conflicts']], ['removed'])
        self.assertEqual(r.data['merged'], 0)

    def test_stock_cap_is_surfaced_and_applied(self):
        p = self._product(qty=3)
        r = self._merge([{'product_id': p.id, 'quantity': 10}])
        self.assertEqual(r.status_code, 200)
        caps = [c for c in r.data['conflicts'] if c['kind'] == 'stock_capped']
        self.assertEqual(len(caps), 1)
        self.assertIn('3', caps[0]['detail'])
        # the quantity was actually capped, not just reported
        self.assertEqual(
            CartItem.objects.get(cart__user=self.user, product=p).quantity, 3)

    def test_price_change_is_surfaced_never_silent(self):
        p = self._product(price='1500.00')
        r = self._merge([{'product_id': p.id, 'quantity': 1,
                          'price_at_add': '1000.00'}])
        changed = [c for c in r.data['conflicts'] if c['kind'] == 'price_changed']
        self.assertEqual(len(changed), 1)
        # the stored price is the CURRENT one, not the stale guest price
        item = CartItem.objects.get(cart__user=self.user, product=p)
        self.assertEqual(item.price_at_add, Decimal('1500.00'))

    def test_merge_sums_into_existing_user_cart(self):
        p = self._product(qty=10)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=p, quantity=1,
                                price_at_add=p.price)
        r = self._merge([{'product_id': p.id, 'quantity': 2}])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            CartItem.objects.get(cart=cart, product=p).quantity, 3)  # 1 + 2

    def test_idempotent_retry_is_noop(self):
        # A retried merge (lost response on a flaky Angolan network) carries
        # the SAME Idempotency-Key → the cached response replays, the
        # quantity is NOT doubled (Guest-First doc CH12).
        p = self._product(qty=10)
        payload = {'items': [{'product_id': p.id, 'quantity': 2}]}
        key = 'merge-login-abc123'
        self.client.post('/api/v1/cart/merge/', payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=key)
        self.client.post('/api/v1/cart/merge/', payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(
            CartItem.objects.get(cart__user=self.user, product=p).quantity, 2)
