"""
Admin permission matrix conformance test (Admin UI & Backend doc CH4.3).

CH4.3 mandates: lock the admin permission matrix with a spec-derived,
parametrised conformance test that asserts every level grants EXACTLY its
specified permissions and denies the rest, with explicit checks that the most
dangerous powers are owner-only and that no lower level can escalate. "The
test IS the matrix, executable, so any accidental grant or missed denial fails
CI." This is the same remedy that locked the seller matrix.

EXPECTED_MIN_LEVEL below is transcribed directly from the doc's CH4.2 table —
it is the SPEC, not a copy of the implementation, so a drift in either
direction (an added grant or a missed denial) is caught.
"""
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model

from apps.admin_console.permissions import (
    ADMIN_PERMISSION_MIN_LEVEL,
    L6_ONLY_PERMISSIONS,
    permissions_for_level,
    has_admin_permission,
)

# Doc CH4.2 — granular permission -> minimum level, transcribed from the table.
# Independent of the implementation on purpose: this is the spec the
# implementation must match.
EXPECTED_MIN_LEVEL = {
    'user.view': 1,
    'order.view': 1,
    'user.view.pii': 4,
    'kyc.view.documents': 4,
    'kyc.review': 4,
    'refund.issue': 3,
    'refund.high_value': 4,
    'payout.approve': 4,
    'user.suspend': 3,
    'seller.suspend': 3,
    'user.impersonate': 3,
    'config.edit': 5,
    'flag.toggle': 5,
    'config.edit.critical': 6,
    'admin_user.manage': 6,
    'audit.view': 6,
}

LEVELS = [1, 2, 3, 4, 5, 6]


class AdminPermissionMatrixConformance(SimpleTestCase):
    def test_catalogue_matches_spec_exactly(self):
        # No permission added or removed vs the spec without updating both.
        self.assertEqual(
            set(ADMIN_PERMISSION_MIN_LEVEL), set(EXPECTED_MIN_LEVEL),
            'admin permission catalogue drifted from the doc CH4.2 spec',
        )

    def test_every_cell_matches_the_spec(self):
        # For every (permission, level) cell, the implemented bundle must grant
        # exactly the spec's grants and deny exactly its non-grants.
        for permission, min_level in EXPECTED_MIN_LEVEL.items():
            for level in LEVELS:
                expected = level >= min_level
                with self.subTest(permission=permission, level=level):
                    self.assertEqual(
                        permission in permissions_for_level(level), expected,
                        f"L{level} {'should' if expected else 'should NOT'} "
                        f"hold {permission}",
                    )

    def test_owner_only_powers_are_l6_only(self):
        # The most dangerous powers: denied at L1..L5, held only at L6.
        for permission in sorted(L6_ONLY_PERMISSIONS):
            for level in [1, 2, 3, 4, 5]:
                with self.subTest(permission=permission, level=level):
                    self.assertNotIn(permission, permissions_for_level(level))
            self.assertIn(permission, permissions_for_level(6))

    def test_l6_only_set_matches_spec(self):
        spec_l6 = {p for p, lvl in EXPECTED_MIN_LEVEL.items() if lvl == 6}
        self.assertEqual(L6_ONLY_PERMISSIONS, spec_l6)

    def test_no_privilege_escalation_lower_is_subset_of_higher(self):
        # A lower level's bundle is always a strict subset of a higher level's:
        # no lower role can reach a permission a higher one holds.
        for lo, hi in zip(LEVELS, LEVELS[1:]):
            with self.subTest(lo=lo, hi=hi):
                self.assertTrue(
                    permissions_for_level(lo) <= permissions_for_level(hi))

    def test_unknown_permission_denied_by_default(self):
        # Deny-by-default: an unknown permission is never granted, even to L6.
        self.assertNotIn('does.not.exist', permissions_for_level(6))
        self.assertFalse(has_admin_permission(None, 'does.not.exist'))


class AdminPermissionEnforcement(TestCase):
    """has_admin_permission resolves the real staff principal's level
    (services.admin_level) and checks the matrix — the CH5 Layer-2 gate."""

    def test_level_3_finance_op_bundle(self):
        from apps.admin_console.models import AdminRoleAssignment
        User = get_user_model()
        u = User.objects.create_user(email='l3@micha.test', password='x')
        u.is_staff = True
        u.save(update_fields=['is_staff'])
        AdminRoleAssignment.objects.create(admin=u, level=3, is_active=True)

        # Held at L3
        self.assertTrue(has_admin_permission(u, 'user.view'))
        self.assertTrue(has_admin_permission(u, 'refund.issue'))
        self.assertTrue(has_admin_permission(u, 'user.suspend'))
        # Denied below the threshold
        self.assertFalse(has_admin_permission(u, 'payout.approve'))   # L4
        self.assertFalse(has_admin_permission(u, 'config.edit'))      # L5
        self.assertFalse(has_admin_permission(u, 'admin_user.manage'))  # L6
        self.assertFalse(has_admin_permission(u, 'audit.view'))       # L6

    def test_superuser_holds_everything(self):
        User = get_user_model()
        su = User.objects.create_user(email='root@micha.test', password='x')
        su.is_staff = True
        su.is_superuser = True
        su.save(update_fields=['is_staff', 'is_superuser'])
        for permission in EXPECTED_MIN_LEVEL:
            with self.subTest(permission=permission):
                self.assertTrue(has_admin_permission(su, permission))
