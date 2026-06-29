"""
Admin permission matrix — the single source of truth (Admin UI & Backend doc CH4).

The console has a 6-level role hierarchy (``AdminRoleAssignment.level``, 1..6;
see ``services.admin_level``). The doc's CH4.2 matrix defines, per granular
action permission, the MINIMUM level that holds it — the hierarchy is
cumulative, so a higher level holds every lower level's permissions plus its
own. This module encodes that matrix as data the authz layer reads, and it is
LOCKED by a parametrised conformance test (``tests_admin_matrix.py``) so an
accidental grant or missed denial fails CI — the CH4.3 mandate, the same
remedy already applied to the seller matrix (``seller_operations``).

The most dangerous powers are L6-only and asserted owner-only by the test:
  - ``admin_user.manage``    — controls WHO has power (escalation root)
  - ``config.edit.critical`` — payment/security levers
  - ``audit.view``           — the audit trail is evidence (Audit doc CH11)

NOTE ON SCOPING (doc CH4.2 asterisks): a few permissions are domain-scoped at
L2/L3 (e.g. an L2 KYC specialist may review KYC while an L2 moderator may not).
The pure level matrix below encodes the UNCONDITIONAL threshold (the level at
which the permission is held regardless of function); earlier function-scoped
access is a documented follow-on layered on top via ``AdminRoleAssignment.
function``. Encoding the unconditional threshold is the conservative, lockable
baseline (it never over-grants).
"""

# Granular permission -> minimum admin level that holds it (doc CH4.2 table).
# This is the single source of truth; tests_admin_matrix.py locks it against
# an independently-typed copy of the spec grid.
ADMIN_PERMISSION_MIN_LEVEL = {
    # ── Read (everyone in the console) ──
    'user.view': 1,
    'order.view': 1,
    # ── Sensitive PII / KYC docs (L4 unconditional; L2/L3 only if scoped) ──
    'user.view.pii': 4,
    'kyc.view.documents': 4,
    'kyc.review': 4,
    # ── Money within limit ──
    'refund.issue': 3,
    # ── High-value money (segregation — doc CH7) ──
    'refund.high_value': 4,
    'payout.approve': 4,
    # ── Account lifecycle ──
    'user.suspend': 3,
    'seller.suspend': 3,
    'user.impersonate': 3,
    # ── Platform configuration ──
    'config.edit': 5,
    'flag.toggle': 5,
    # ── Owner-only (L6) — the most dangerous powers ──
    'config.edit.critical': 6,
    'admin_user.manage': 6,
    'audit.view': 6,
}

# The L6-only protections, called out explicitly so the conformance test can
# assert no lower level ever holds them (the "missing owner-only protection"
# failure mode the doc warns about).
L6_ONLY_PERMISSIONS = frozenset({
    'config.edit.critical',
    'admin_user.manage',
    'audit.view',
})


def permissions_for_level(level: int) -> set[str]:
    """The permission bundle a given admin level holds (the role->bundle
    mapping the doc calls the single source of truth). Pure function over the
    matrix — no DB — so the conformance test is fast and deterministic."""
    return {
        perm for perm, min_level in ADMIN_PERMISSION_MIN_LEVEL.items()
        if level >= min_level
    }


def has_admin_permission(admin, permission: str) -> bool:
    """Does this admin hold ``permission``? Resolves the staff principal's
    level via ``services.admin_level`` and checks the matrix. Unknown
    permissions are DENIED by default (deny-by-default — doc CH2)."""
    from .services import admin_level
    min_level = ADMIN_PERMISSION_MIN_LEVEL.get(permission)
    if min_level is None:
        return False
    return admin_level(admin) >= min_level


def RequireAdminPermission(permission: str):
    """DRF permission-class factory for per-action gating (doc CH5 Layer 2).

    Usage on an admin view::

        permission_classes = [RequireAdminPermission('refund.issue')]

    Enforces, server-side: authenticated + staff + holds the granular
    permission. Layered ON TOP of the existing ``IsAdmin`` surface gate, so
    adopting it on an endpoint only ever tightens access, never loosens it.
    """
    from rest_framework.permissions import BasePermission

    class _RequireAdminPermission(BasePermission):
        message = f'Admin permission required: {permission}'

        def has_permission(self, request, view):
            user = getattr(request, 'user', None)
            return bool(
                user and user.is_authenticated
                and getattr(user, 'is_staff', False)
                and has_admin_permission(user, permission)
            )

    _RequireAdminPermission.__name__ = (
        f'RequireAdminPermission_{permission.replace(".", "_")}'
    )
    return _RequireAdminPermission
