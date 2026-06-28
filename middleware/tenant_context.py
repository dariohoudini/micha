"""
middleware/tenant_context.py — set the RLS tenant context per request.

The linchpin of Row-Level Security (Security & RLS doc Part 1 CH8/CH11):
after IAM authentication has resolved the verified principal, this
middleware tells PostgreSQL who that principal is, via a transaction-local
session variable that the RLS policies read. The identity comes ONLY from
``request.user`` (the cryptographically-verified token), never from any
client-supplied value (CH8 trust chain).

Gating (CH11 — RLS is high-risk to enable):
  * Active ONLY when ``settings.RLS_ENABLED`` is True AND the backend is
    PostgreSQL. Off by default → a no-op in dev (SQLite) and until the
    staged production rollout deliberately turns it on. This makes the
    platform RLS-*ready* without risking a default-deny outage.
  * Uses set_config(..., is_local=true) (= SET LOCAL), which is
    transaction-scoped and therefore safe under PgBouncer transaction
    pooling — a plain SET would leak context across pooled connections
    (CH8 pitfall 2). Requires the request to run in a transaction
    (ATOMIC_REQUESTS) so the SET LOCAL covers all of its queries.

Place this AFTER the authentication middleware so request.user is set.
"""
from django.conf import settings
from django.db import connection

from apps.core import rls


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Resolve once: the middleware is a cheap pass-through when RLS is
        # off or the backend can't enforce it.
        self.enabled = bool(getattr(settings, 'RLS_ENABLED', False))

    def __call__(self, request):
        if self.enabled and rls.is_postgres(connection):
            # Identity from the verified principal only (CH8). On an
            # unauthenticated request this sets an empty context → the
            # policies match no rows (fail closed).
            try:
                rls.set_context_for_request(request)
            except Exception:
                # Never break the request over context-setting; unset
                # context fails closed, the safe direction.
                pass
        return self.get_response(request)
