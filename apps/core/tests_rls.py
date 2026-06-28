"""
RLS infrastructure tests (Security & RLS doc Part 1).

What's verifiable in the SQLite dev/CI environment: the tenant-context
trust chain (identity from the verified principal, never client input), the
vendor no-op safety, the policy-SQL template correctness (ENABLE+FORCE,
USING+WITH CHECK, fail-closed helpers), and that the whole thing is OFF by
default so it can't cause a default-deny outage. The end-to-end policy
enforcement is exercised on PostgreSQL during the staged rollout (CH11-12).
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core import rls

User = get_user_model()


class VendorSafetyTests(SimpleTestCase):
    def test_set_context_is_noop_on_sqlite(self):
        # Must not raise on a non-Postgres backend (dev/CI runs SQLite).
        rls.set_tenant_context(user_id='u1', seller_id='s1', role='seller')
        rls.clear_tenant_context()

    def test_is_postgres_matches_actual_backend(self):
        # is_postgres() must track the real connection vendor — not assume the
        # test DB is always SQLite. (The suite runs on SQLite in dev/CI and on
        # PostgreSQL when DB_* env vars are set; both must pass.)
        from django.db import connection
        self.assertEqual(
            rls.is_postgres(connection),
            connection.vendor == 'postgresql',
        )


class HelperSqlTests(SimpleTestCase):
    def test_helper_functions_fail_closed(self):
        sql = rls.helper_functions_sql()
        for fn in ('current_tenant_user', 'current_tenant_seller',
                   'current_tenant_courier', 'current_role_is'):
            self.assertIn(fn, sql)
        # nullif(..., '') → unset context yields NULL → matches no rows.
        self.assertIn("nullif(current_setting", sql)
        self.assertIn('STABLE', sql)


class PolicySqlTests(SimpleTestCase):
    def test_dual_tenancy_table_emits_force_using_and_check(self):
        sql = rls.enable_rls_sql('orders_order', seller_key='seller_id',
                                 user_key='buyer_id')
        self.assertIn('ENABLE ROW LEVEL SECURITY', sql)
        self.assertIn('FORCE ROW LEVEL SECURITY', sql)          # pitfall 3
        # seller + buyer + admin policies present
        self.assertIn('orders_order_seller', sql)
        self.assertIn('orders_order_buyer', sql)
        self.assertIn('orders_order_admin', sql)
        # both read (USING) and write (WITH CHECK) guarded (pitfall 6)
        self.assertIn('USING', sql)
        self.assertIn('WITH CHECK', sql)
        # tenant predicates key on the right columns + context helpers
        self.assertIn("seller_id::text = current_tenant_seller()", sql)
        self.assertIn("buyer_id::text = current_tenant_user()", sql)

    def test_seller_only_table_has_no_buyer_policy(self):
        sql = rls.enable_rls_sql('payments_sellerwallet', user_key='owner_id')
        self.assertIn('payments_sellerwallet_buyer', sql)
        self.assertNotIn('payments_sellerwallet_seller', sql)

    def test_disable_sql_drops_policies_and_rls(self):
        sql = rls.disable_rls_sql('orders_order')
        self.assertIn('DROP POLICY IF EXISTS orders_order_seller', sql)
        self.assertIn('DISABLE ROW LEVEL SECURITY', sql)


class TrustChainTests(TestCase):
    """Context is derived from the VERIFIED principal, never client input."""

    def test_anonymous_is_unset_fail_closed(self):
        class Anon:
            is_authenticated = False
        ctx = rls.context_from_principal(Anon())
        self.assertEqual(ctx['role'], None)
        self.assertEqual(ctx['user_id'], None)

    def test_plain_user_is_buyer(self):
        u = User.objects.create(username='buyer@test.ao', email='buyer@test.ao')
        ctx = rls.context_from_principal(u)
        self.assertEqual(ctx['role'], rls.ROLE_BUYER)
        self.assertEqual(ctx['user_id'], str(u.pk))
        self.assertIsNone(ctx['seller_id'])

    def test_staff_is_admin_cross_tenant(self):
        u = User.objects.create(username='admin@test.ao',
                                email='admin@test.ao', is_staff=True)
        ctx = rls.context_from_principal(u)
        self.assertEqual(ctx['role'], rls.ROLE_ADMIN)

    def test_store_owner_is_seller(self):
        from apps.stores.models import Store
        u = User.objects.create(username='seller@test.ao',
                                email='seller@test.ao')
        Store.objects.create(owner=u, name='RLS Test Store')
        ctx = rls.context_from_principal(u)
        self.assertEqual(ctx['role'], rls.ROLE_SELLER)
        self.assertEqual(ctx['seller_id'], str(u.pk))


class GatingTests(SimpleTestCase):
    def test_rls_off_by_default(self):
        # High-risk feature: must not be on unless deliberately enabled.
        self.assertFalse(settings.RLS_ENABLED)

    def test_middleware_registered(self):
        self.assertIn('middleware.tenant_context.TenantContextMiddleware',
                      settings.MIDDLEWARE)
