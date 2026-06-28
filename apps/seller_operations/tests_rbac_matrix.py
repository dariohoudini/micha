"""
Seller RBAC matrix conformance test (IAM/RBAC doc Part 2 CH17 + CH29).

CH29 mandates: "parametrised test asserting each role's permission set matches
the matrices (CH17, CH18) exactly — catches accidental grants." This locks
seller_operations.ROLE_PERMISSIONS to the doc's CH17 matrix so any future
edit that over- or under-grants a permission fails CI.

The EXPECTED_MATRIX below is transcribed directly from the doc's CH17 table
and CH30 catalogue — it is the spec, not a copy of the implementation, so a
drift in either direction is caught.
"""
from django.test import SimpleTestCase

from apps.seller_operations.models import (
    ALL_SELLER_PERMISSIONS, ROLE_PERMISSIONS,
)

# Doc CH30 — the 21-permission seller catalogue (authoritative vocabulary).
EXPECTED_CATALOGUE = {
    'manage_listings', 'view_listings', 'manage_variants', 'view_orders',
    'process_orders', 'mark_shipped', 'print_packing_slip', 'issue_refund',
    'approve_refund', 'view_financials', 'manage_bank_account', 'request_payout',
    'respond_messages', 'bulk_message', 'manage_promotions', 'manage_repricing',
    'manage_staff', 'view_analytics', 'manage_return_policy',
    'manage_integrations', 'close_store',
}

# Doc CH17 — per-role grants, transcribed from the matrix table.
EXPECTED_MATRIX = {
    'owner': set(EXPECTED_CATALOGUE),  # owner holds everything
    'manager': {
        'manage_listings', 'view_listings', 'manage_variants', 'view_orders',
        'process_orders', 'mark_shipped', 'print_packing_slip', 'issue_refund',
        'approve_refund', 'view_financials', 'respond_messages', 'bulk_message',
        'manage_promotions', 'manage_repricing', 'view_analytics',
        'manage_return_policy', 'manage_integrations',
    },
    'cs_agent': {'view_listings', 'view_orders', 'respond_messages'},
    'warehouse': {
        'view_listings', 'manage_variants', 'view_orders', 'process_orders',
        'mark_shipped', 'print_packing_slip',
    },
    'listings_only': {
        'manage_listings', 'view_listings', 'manage_variants', 'manage_repricing',
    },
}

# Owner-only permissions per CH17 "OWNER PROTECTIONS" — staff never hold these.
OWNER_ONLY = {'manage_staff', 'manage_bank_account', 'request_payout',
              'close_store'}


class SellerRbacMatrixTests(SimpleTestCase):
    def test_catalogue_matches_doc(self):
        self.assertEqual(set(ALL_SELLER_PERMISSIONS), EXPECTED_CATALOGUE)

    def test_every_role_matches_ch17_exactly(self):
        # Same role set, no extras, no missing roles.
        self.assertEqual(set(ROLE_PERMISSIONS), set(EXPECTED_MATRIX))
        for role, expected in EXPECTED_MATRIX.items():
            with self.subTest(role=role):
                actual = set(ROLE_PERMISSIONS[role])
                over = actual - expected
                under = expected - actual
                self.assertEqual(actual, expected,
                                 f"{role}: over-granted={over} under-granted={under}")

    def test_no_role_grants_unknown_permission(self):
        for role, perms in ROLE_PERMISSIONS.items():
            with self.subTest(role=role):
                unknown = set(perms) - EXPECTED_CATALOGUE
                self.assertFalse(unknown, f"{role} grants unknown perms: {unknown}")

    def test_owner_only_permissions_never_held_by_staff(self):
        for role in ('manager', 'cs_agent', 'warehouse', 'listings_only'):
            with self.subTest(role=role):
                leaked = OWNER_ONLY & set(ROLE_PERMISSIONS[role])
                self.assertFalse(leaked,
                                 f"{role} must not hold owner-only perms: {leaked}")

    def test_cs_agent_cannot_refund_or_see_financials(self):
        # The doc's headline example: a CS agent answers messages but cannot
        # issue refunds or touch financials.
        cs = set(ROLE_PERMISSIONS['cs_agent'])
        for forbidden in ('issue_refund', 'approve_refund', 'view_financials',
                          'manage_listings', 'manage_staff'):
            self.assertNotIn(forbidden, cs)

    def test_warehouse_cannot_price_or_refund(self):
        wh = set(ROLE_PERMISSIONS['warehouse'])
        for forbidden in ('manage_promotions', 'manage_repricing', 'issue_refund',
                          'respond_messages', 'view_financials'):
            self.assertNotIn(forbidden, wh)
