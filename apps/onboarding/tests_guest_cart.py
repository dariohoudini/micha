"""
Guest-First doc CH6 — the server-side guest cart + the signup merge.

Locks: the anon cart snapshot round-trips (PUT replace-idempotent, GET
re-validated against the live catalog in the user-cart item shape), and
at signup the snapshot folds into the account Cart with /cart/merge/
semantics (dead items skipped, quantity clamped, current price stored)
then retires — so a retried carry-over can't double the cart.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cart.models import CartItem
from apps.onboarding.models import GuestCartItem, GuestProfile
from apps.onboarding.services import carry_over_guest_profile
from apps.products.models import Product
from apps.stores.models import Store

User = get_user_model()
DEV = 'guestcart-dev-1'


class GuestCartApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()   # anonymous — the guest surface
        seller = User.objects.create_user(
            email='v@test.ao', password='pw12345678!', username='v',
            is_seller=True)
        self.store = Store.objects.create(owner=seller, name='Loja')
        self.p = Product.objects.create(
            store=self.store, title='Ventoinha', description='x',
            price=Decimal('7500.00'), quantity=5, is_active=True)

    def _put(self, items, dev=DEV):
        return self.client.put('/api/v1/guest/cart/',
                               {'device_id': dev, 'items': items},
                               format='json')

    def test_put_get_roundtrip_in_user_cart_shape(self):
        r = self._put([{'product_id': self.p.id, 'quantity': 2,
                        'price_at_add': '7500.00', 'title': 'Ventoinha'}])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['saved'], 1)
        g = self.client.get('/api/v1/guest/cart/', {'device_id': DEV})
        self.assertEqual(len(g.data['items']), 1)
        item = g.data['items'][0]
        self.assertEqual(item['product'], self.p.id)
        self.assertEqual(item['product_title'], 'Ventoinha')
        self.assertEqual(item['product_price'], '7500.00')  # current price
        self.assertEqual(item['quantity'], 2)

    def test_put_is_a_replace_never_a_double(self):
        payload = [{'product_id': self.p.id, 'quantity': 2}]
        self._put(payload)
        self._put(payload)   # same snapshot again
        self.assertEqual(GuestCartItem.objects.filter(
            guest__device_id=DEV).get().quantity, 2)

    def test_get_skips_products_gone_since_snapshot(self):
        dead = Product.objects.create(
            store=self.store, title='Morto', description='x',
            price=Decimal('100.00'), quantity=1, is_active=True)
        self._put([{'product_id': self.p.id, 'quantity': 1},
                   {'product_id': dead.id, 'quantity': 1}])
        dead.is_active = False
        dead.save()
        g = self.client.get('/api/v1/guest/cart/', {'device_id': DEV})
        self.assertEqual([i['product'] for i in g.data['items']], [self.p.id])

    def test_garbage_rows_skipped(self):
        r = self._put([{'product_id': 'abc'}, {'quantity': 3}, 'nonsense',
                       {'product_id': self.p.id, 'quantity': 1}])
        self.assertEqual(r.data['saved'], 1)


class SignupMergeTests(TestCase):

    def setUp(self):
        seller = User.objects.create_user(
            email='v2@test.ao', password='pw12345678!', username='v2',
            is_seller=True)
        self.store = Store.objects.create(owner=seller, name='Loja2')
        self.p = Product.objects.create(
            store=self.store, title='Colchão', description='x',
            price=Decimal('40000.00'), quantity=3, is_active=True)
        self.gp = GuestProfile.objects.create(device_id=DEV)

    def test_signup_merge_folds_snapshot_into_user_cart(self):
        GuestCartItem.objects.create(guest=self.gp, product_id=self.p.id,
                                     quantity=10)   # over stock (3)
        user = User.objects.create_user(email='m@test.ao',
                                        password='pw12345678!', username='m')
        carry_over_guest_profile(user, DEV)
        item = CartItem.objects.get(cart__user=user, product=self.p)
        self.assertEqual(item.quantity, 3)                    # clamped
        self.assertEqual(item.price_at_add, Decimal('40000.00'))  # current
        # snapshot retired → a retried carry-over cannot double
        self.assertEqual(self.gp.cart_items.count(), 0)

    def test_merge_sums_into_existing_user_row(self):
        from apps.cart.models import Cart
        GuestCartItem.objects.create(guest=self.gp, product_id=self.p.id,
                                     quantity=1)
        user = User.objects.create_user(email='m2@test.ao',
                                        password='pw12345678!', username='m2')
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=self.p, quantity=1,
                                price_at_add=self.p.price)
        carry_over_guest_profile(user, DEV)
        self.assertEqual(CartItem.objects.get(cart=cart, product=self.p)
                         .quantity, 2)   # 1 + 1

    def test_dead_snapshot_items_skipped_safely(self):
        GuestCartItem.objects.create(guest=self.gp, product_id=999999,
                                     quantity=1)
        user = User.objects.create_user(email='m3@test.ao',
                                        password='pw12345678!', username='m3')
        gp = carry_over_guest_profile(user, DEV)
        self.assertEqual(gp.linked_user_id, user.id)   # carry-over still lands
        self.assertFalse(CartItem.objects.filter(cart__user=user).exists())
