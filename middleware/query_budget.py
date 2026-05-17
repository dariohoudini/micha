"""
middleware/query_budget.py

Per-tenant DB-query budget — defends the cluster against accidental or
adversarial query storms from a single caller. Complementary to DRF
throttling (which counts requests, not work-per-request).

How it works:
  • Every request that hits the API path runs through QueryAuditMiddleware
    already (apps/telemetry/query_audit.py) — it tags request._db_queries
    with the DB-query count for that request.
  • QueryBudgetMiddleware (this module) reads that count at response time
    and adds it to a sliding 60-second per-tenant counter in cache.
  • When a tenant exceeds BUDGET_QUERIES_PER_MIN in any 60s window, the
    NEXT request gets a 429 with a clear error and a Retry-After hint.
  • The current request always passes — we never half-deny a response.
    Budget overruns block the NEXT request; this preserves the property
    that any single accepted request completes normally.

Tenant key:
  • Authenticated user → user:<id>
  • Anon              → ip:<ip> (best-effort; behind CDN trust X-Forwarded-For)
  • Admin             → exempt (operations work shouldn't trip the budget)

Failure mode: cache backend down → middleware no-ops cleanly. We'd
rather over-serve under a Redis outage than under-serve.
"""
from __future__ import annotations
import logging

from django.http import JsonResponse
from django.core.cache import cache

log = logging.getLogger(__name__)


# Defaults — tunable per-route via Settings if needed
BUDGET_WINDOW_SECONDS = 60
BUDGET_QUERIES_PER_MIN = 5000   # 80+ queries/sec sustained — clearly abusive
WARN_AT_PCT = 75                 # log a warning when 75% consumed (early signal)


class QueryBudgetMiddleware:
    """Enforces a DB-query budget per tenant per minute. Runs LATE in the
    chain (after auth + telemetry) so request.user and request._db_queries
    are populated."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Pre-flight: if this tenant is already over budget, refuse early.
        if request.path.startswith('/api/'):
            tenant_key = self._tenant_key(request)
            if tenant_key and not self._is_admin(request):
                consumed, ttl = self._get_consumed(tenant_key)
                if consumed >= BUDGET_QUERIES_PER_MIN:
                    return JsonResponse({
                        'error': 'query_budget_exceeded',
                        'detail': (
                            f'You have exceeded the query budget of '
                            f'{BUDGET_QUERIES_PER_MIN} per {BUDGET_WINDOW_SECONDS}s. '
                            f'Slow down and retry.'
                        ),
                        'retry_after_seconds': max(1, ttl),
                        'budget_per_window': BUDGET_QUERIES_PER_MIN,
                        'window_seconds': BUDGET_WINDOW_SECONDS,
                    }, status=429, headers={'Retry-After': str(max(1, ttl))})

        response = self.get_response(request)

        # Post-flight: bump the counter by this request's DB-query count.
        if request.path.startswith('/api/'):
            tenant_key = self._tenant_key(request)
            if tenant_key and not self._is_admin(request):
                queries = int(getattr(request, '_db_queries', 0) or 0)
                if queries > 0:
                    new_total = self._bump(tenant_key, queries)
                    if new_total >= BUDGET_QUERIES_PER_MIN * WARN_AT_PCT // 100:
                        log.warning(
                            'query_budget_approaching: tenant=%s used=%d/%d',
                            tenant_key, new_total, BUDGET_QUERIES_PER_MIN,
                        )
        return response

    # ── Internals ──────────────────────────────────────────────────────

    def _tenant_key(self, request) -> str:
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            return f'qb:user:{user.id}'
        ip = self._client_ip(request)
        return f'qb:ip:{ip}' if ip else ''

    def _is_admin(self, request) -> bool:
        u = getattr(request, 'user', None)
        return bool(u and getattr(u, 'is_authenticated', False)
                    and (getattr(u, 'is_staff', False) or getattr(u, 'is_superuser', False)))

    def _client_ip(self, request) -> str:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        return (xff.split(',')[0].strip() if xff else (request.META.get('REMOTE_ADDR') or ''))[:45]

    def _get_consumed(self, tenant_key: str) -> tuple[int, int]:
        """Returns (consumed_count, ttl_remaining_seconds). Cache failure
        → (0, 0): treat as not-over-budget, log nothing."""
        try:
            v = cache.get(tenant_key, 0)
            return int(v or 0), BUDGET_WINDOW_SECONDS  # approximate TTL
        except Exception:
            return 0, 0

    def _bump(self, tenant_key: str, delta: int) -> int:
        """Atomically add ``delta`` to the counter. First call initialises
        with TTL=BUDGET_WINDOW_SECONDS so the window slides. Returns new total.

        Uses cache.add + cache.incr — Redis atomic. Cache failure → no
        budget tracking for this request (degrade open)."""
        try:
            cache.add(tenant_key, 0, timeout=BUDGET_WINDOW_SECONDS)
            return int(cache.incr(tenant_key, delta) or 0)
        except Exception:
            return 0
