"""
apps/core/rls.py — Row-Level Security tenant context + policy tooling.

Implements the database-layer tenant-isolation backstop from the Security &
RLS spec (Part 1, Part C). RLS makes PostgreSQL itself refuse to return
another tenant's rows, so even a forgotten app-layer ownership filter (the
classic IDOR) becomes a non-event instead of a cross-tenant breach.

This module provides the two halves the spec calls for:

  1. TENANT CONTEXT (CH8 — "the linchpin"): every request tells the database
     who the *verified* principal is, via a transaction-local session
     variable that the RLS policies read. We use ``set_config(key, val,
     is_local=true)`` — the function form of ``SET LOCAL`` — which is scoped
     to the current transaction and therefore SAFE under PgBouncer
     transaction pooling (a plain ``SET`` would leak across pooled
     connections → cross-tenant breach, CH8 pitfall 2). The identity comes
     ONLY from ``request.user`` (the IAM-verified principal), never from
     client-supplied values.

  2. POLICY SQL BUILDERS (CH9-11): a uniform template that generates the
     ENABLE + FORCE + per-principal policies for a protected table, so the
     staged per-table rollout (CH11) is a reviewed one-liner in a migration.

SAFETY / ROLLOUT (CH11 — RLS is high-risk to enable):
  * Everything here is a NO-OP on non-PostgreSQL backends (SQLite dev).
  * The request middleware that sets context is gated behind
    ``settings.RLS_ENABLED`` (default False) so the platform is RLS-*ready*
    without flipping the switch — enabling RLS on production tables is the
    deliberate, staged, staging-tested operation the spec mandates, not a
    blanket default that could cause a default-deny outage.

Fail-closed: when the context is unset, the helper functions return NULL,
which matches NO rows under the policies (CH8) — the safe failure direction.
"""
from __future__ import annotations

from django.db import connection

# Session-variable names the policies read (CH8). All transaction-local.
KEY_USER_ID = 'app.current_user_id'
KEY_SELLER_ID = 'app.current_seller_id'
KEY_COURIER_ID = 'app.current_courier_id'
KEY_ROLE = 'app.current_role'

# Principal roles the policies branch on (mirrors IAM doc principal types).
ROLE_BUYER = 'buyer'
ROLE_SELLER = 'seller'
ROLE_ADMIN = 'admin'
ROLE_COURIER = 'courier'


def is_postgres(conn=None) -> bool:
    return (conn or connection).vendor == 'postgresql'


# ---------------------------------------------------------------------------
# Tenant context (CH8) — set per request, transaction-local, fail-closed.
# ---------------------------------------------------------------------------
def set_tenant_context(*, user_id=None, seller_id=None, courier_id=None,
                       role=None, conn=None):
    """Set the transaction-local tenant context the RLS policies read.

    Uses set_config(..., is_local=true) so the values are scoped to the
    current transaction and cannot leak onto a pooled connection (CH8).
    No-op on non-PostgreSQL backends. Never raises — a context-setting
    failure must not break the request (and unset context fails closed).
    """
    conn = conn or connection
    if not is_postgres(conn):
        return
    pairs = [
        (KEY_USER_ID, user_id),
        (KEY_SELLER_ID, seller_id),
        (KEY_COURIER_ID, courier_id),
        (KEY_ROLE, role),
    ]
    try:
        with conn.cursor() as cur:
            for key, value in pairs:
                # Empty string when unset → helper functions return NULL →
                # policies match no rows (fail closed, CH8).
                cur.execute("SELECT set_config(%s, %s, true)",
                            [key, '' if value is None else str(value)])
    except Exception:
        # Defensive: never let context-setting take down a request. The
        # policies fail closed on unset context, so the safe direction holds.
        pass


def clear_tenant_context(conn=None):
    """Reset the context to unset (NULL → no rows). Belt-and-braces; SET
    LOCAL already auto-resets at transaction end."""
    set_tenant_context(conn=conn)


def context_from_principal(user):
    """Derive the tenant context dict from a VERIFIED principal (request.user
    set by IAM authentication, IAM doc CH9) — NEVER from client input.

    Returns the kwargs for set_tenant_context. Resolution:
      * staff / superuser  -> admin (cross-tenant, audited at the app layer)
      * owns/acts-as seller -> seller + their seller (store owner) id
      * otherwise           -> buyer
    Anonymous / no user -> all None (unset → fail closed).
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return {'user_id': None, 'seller_id': None, 'courier_id': None,
                'role': None}

    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return {'user_id': str(user.pk), 'seller_id': None,
                'courier_id': None, 'role': ROLE_ADMIN}

    seller_id = _resolve_seller_id(user)
    if seller_id is not None:
        return {'user_id': str(user.pk), 'seller_id': str(seller_id),
                'courier_id': None, 'role': ROLE_SELLER}

    return {'user_id': str(user.pk), 'seller_id': None, 'courier_id': None,
            'role': ROLE_BUYER}


def _resolve_seller_id(user):
    """The principal's seller tenant id, if they own/act-as a seller.

    Seller tenancy keys on the store owner (Order.seller / Store.owner is a
    User in this codebase), so the tenant id is the user's own pk when they
    have a store. Returns None for pure buyers. Fail-open to buyer on any
    lookup error (the app layer still scopes; this only affects RLS).
    """
    try:
        from apps.stores.models import Store
        if Store.objects.filter(owner=user).exists():
            return user.pk
    except Exception:
        pass
    return None


def set_context_for_request(request, conn=None):
    """Convenience: resolve + apply context for an HTTP request."""
    ctx = context_from_principal(getattr(request, 'user', None))
    set_tenant_context(conn=conn, **ctx)
    return ctx


# ---------------------------------------------------------------------------
# Helper-function SQL (CH8) — the STABLE functions the policies call.
# ---------------------------------------------------------------------------
def helper_functions_sql() -> str:
    """CREATE the STABLE helper functions the policies read context through.
    nullif(..., '') so an unset context yields NULL (no rows = fail closed)."""
    return """
    CREATE OR REPLACE FUNCTION current_tenant_user() RETURNS text AS $$
      SELECT nullif(current_setting('app.current_user_id', true), '');
    $$ LANGUAGE sql STABLE;

    CREATE OR REPLACE FUNCTION current_tenant_seller() RETURNS text AS $$
      SELECT nullif(current_setting('app.current_seller_id', true), '');
    $$ LANGUAGE sql STABLE;

    CREATE OR REPLACE FUNCTION current_tenant_courier() RETURNS text AS $$
      SELECT nullif(current_setting('app.current_courier_id', true), '');
    $$ LANGUAGE sql STABLE;

    CREATE OR REPLACE FUNCTION current_role_is(want text) RETURNS boolean AS $$
      SELECT nullif(current_setting('app.current_role', true), '') = want;
    $$ LANGUAGE sql STABLE;
    """


def drop_helper_functions_sql() -> str:
    return """
    DROP FUNCTION IF EXISTS current_tenant_user();
    DROP FUNCTION IF EXISTS current_tenant_seller();
    DROP FUNCTION IF EXISTS current_tenant_courier();
    DROP FUNCTION IF EXISTS current_role_is(text);
    """


# ---------------------------------------------------------------------------
# Per-table policy SQL builder (CH9-11) — uniform, reviewable template.
# ---------------------------------------------------------------------------
def enable_rls_sql(table: str, *, seller_key: str | None = None,
                   user_key: str | None = None, courier_key: str | None = None,
                   admin: bool = True, force: bool = True) -> str:
    """Build the ENABLE + FORCE + per-principal policy SQL for a protected
    table (CH9-10). Pass the owner column(s) present on the table:

        enable_rls_sql('orders_order', seller_key='seller_id',
                       user_key='buyer_id')         # dual tenancy
        enable_rls_sql('payments_sellerwallet', user_key='owner_id')

    USING + WITH CHECK are both emitted so a tenant can neither READ nor
    WRITE another tenant's row (CH7/CH9, pitfall 6). FORCE makes even the
    table owner subject to policies (pitfall 3). Admin policy is explicit
    and cross-tenant by design (audited at the app layer, CH9).
    """
    stmts = [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;",
    ]
    if force:
        stmts.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

    safe = table.replace('.', '_')
    if seller_key:
        stmts.append(
            f"CREATE POLICY {safe}_seller ON {table} FOR ALL "
            f"USING (current_role_is('seller') AND "
            f"{seller_key}::text = current_tenant_seller()) "
            f"WITH CHECK (current_role_is('seller') AND "
            f"{seller_key}::text = current_tenant_seller());")
    if user_key:
        stmts.append(
            f"CREATE POLICY {safe}_buyer ON {table} FOR ALL "
            f"USING (current_role_is('buyer') AND "
            f"{user_key}::text = current_tenant_user()) "
            f"WITH CHECK (current_role_is('buyer') AND "
            f"{user_key}::text = current_tenant_user());")
    if courier_key:
        stmts.append(
            f"CREATE POLICY {safe}_courier ON {table} FOR SELECT "
            f"USING (current_role_is('courier') AND "
            f"{courier_key}::text = current_tenant_courier());")
    if admin:
        stmts.append(
            f"CREATE POLICY {safe}_admin ON {table} FOR ALL "
            f"USING (current_role_is('admin')) "
            f"WITH CHECK (current_role_is('admin'));")
    return "\n".join(stmts)


def disable_rls_sql(table: str, *, seller=True, buyer=True, courier=False,
                    admin=True) -> str:
    safe = table.replace('.', '_')
    stmts = []
    for cond, suffix in ((seller, 'seller'), (buyer, 'buyer'),
                         (courier, 'courier'), (admin, 'admin')):
        if cond:
            stmts.append(f"DROP POLICY IF EXISTS {safe}_{suffix} ON {table};")
    stmts.append(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    return "\n".join(stmts)
