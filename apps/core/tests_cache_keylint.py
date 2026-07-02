"""
Gap-Coverage CH9A — cache-key safety lint for per-user namespaces.

A per-user cache key that omits the principal id serves one user's data
to another. The guard is structural: per-user namespaces are built ONLY
through build_user_key (which refuses a missing principal), and plain
build_key refuses registered per-user prefixes outright. These tests are
the keep-it-that-way lock.
"""
from django.test import SimpleTestCase

from apps.core.cache_kit import (
    PER_USER_PREFIXES, build_key, build_user_key, register_per_user_prefix,
)


class CacheKeyLintTests(SimpleTestCase):

    def setUp(self):
        self._saved = set(PER_USER_PREFIXES)
        PER_USER_PREFIXES.clear()

    def tearDown(self):
        PER_USER_PREFIXES.clear()
        PER_USER_PREFIXES.update(self._saved)

    def test_user_key_requires_principal(self):
        for missing in (None, '', 0):
            with self.assertRaises(ValueError):
                build_user_key('wishlist', missing, (), 'page1')

    def test_user_key_embeds_principal(self):
        key = build_user_key('wishlist', 42, (), 'page1')
        self.assertIn(':u42:', key)
        self.assertTrue(key.startswith('wishlist:'))

    def test_long_user_key_hash_keeps_principal(self):
        # Even when the composite key overflows and gets hashed, the
        # principal must survive OUTSIDE the hash — two users' long keys
        # can never collide into one cache slot.
        long_part = 'x' * 500
        k1 = build_user_key('feed', 1, (), long_part)
        k2 = build_user_key('feed', 2, (), long_part)
        self.assertNotEqual(k1, k2)
        self.assertIn(':u1:', k1)
        self.assertIn(':u2:', k2)

    def test_build_key_refuses_registered_per_user_prefix(self):
        register_per_user_prefix('orders_mine')
        with self.assertRaises(ValueError):
            build_key('orders_mine', (), 'page1')

    def test_build_user_key_auto_registers_prefix(self):
        build_user_key('recent_views', 7, ())
        self.assertIn('recent_views', PER_USER_PREFIXES)
        with self.assertRaises(ValueError):
            build_key('recent_views', (), 'anything')

    def test_shared_prefixes_unaffected(self):
        key = build_key('product_detail', (), 123)
        self.assertTrue(key.startswith('product_detail:'))
