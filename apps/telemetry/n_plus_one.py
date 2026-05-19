"""
apps/telemetry/n_plus_one.py
─────────────────────────────

N+1 query detection for Django requests.

Why this exists separately from the existing query_audit middleware:

  • query_audit counts TOTAL queries per request. 30 queries can be
    fine (complex page, many denormalised reads) or a problem (one
    template ran 30 times because a serializer accesses .product
    without prefetch_related).

  • Total-count thresholds catch the second case but miss the first.
    A more accurate signal is "did the SAME SQL TEMPLATE run > N
    times?" — that's the actual N+1 signature.

  • This module's detector fingerprints each query down to its
    template (parameters stripped), counts per-fingerprint within
    the request, and flags fingerprints that exceed a threshold.

Three production-grade integration points:

  1. **Middleware**: ``NPlusOneMiddleware`` wires into the existing
     query-audit state and logs WARN-level findings during requests.

  2. **Per-view budget**: A view can declare
     ``db_query_budget = 10`` as a class attribute. The middleware
     enforces it at response time (warn or raise depending on
     settings.DB_QUERY_BUDGET_STRICT).

  3. **Test helper**: ``assert_query_count(max=N)`` context manager
     for pytest — CI fails if a PR pushes a request's query count
     above the documented budget.

Settings:
  N_PLUS_ONE_THRESHOLD          (default 5) — repeats before flagging
  N_PLUS_ONE_LOG_LEVEL          (default 'WARNING')
  DB_QUERY_BUDGET_STRICT        (default False) — True raises on
                                  budget breach instead of warning.
                                  Set in CI; leave off in production.
"""
from __future__ import annotations

import logging
import re
import threading
from contextlib import contextmanager
from typing import Optional

from django.conf import settings
from django.db import connection


log = logging.getLogger('n-plus-one')


# How many repeats of the same template before we call it N+1.
# Default is 5 because some legitimate patterns (lookup-then-update
# pairs in a small loop) can produce 2-3 reps that aren't problems.
DEFAULT_THRESHOLD = 5


# Per-thread state — shared with query_audit's hook.
_local = threading.local()


# ─── Template fingerprinting ──────────────────────────────────────────────

# Strip everything that varies per-row so two queries that differ only
# in parameter values produce the same fingerprint.
_PARAM_PLACEHOLDERS = re.compile(
    r"""
    %s |             # psycopg %s placeholder
    \?  |            # sqlite ? placeholder
    \$\d+ |          # PostgreSQL numbered params
    '[^']*' |        # quoted literals
    \b\d+\b          # bare integers
    """,
    re.VERBOSE,
)
_WHITESPACE = re.compile(r'\s+')
_IN_LIST = re.compile(r'\bIN\s*\([^)]+\)', re.IGNORECASE)


def fingerprint_sql(sql: str) -> str:
    """Reduce a SQL statement to a parameter-free template.

    Two queries that differ only by their parameter values produce
    byte-identical fingerprints. That's what lets us detect N+1:
    fetching N products by ID produces N queries with the SAME
    fingerprint but different param values.

    Returns a single-line, lower-cased, normalised template string.
    Capped at 200 chars so log records stay readable.
    """
    if not sql:
        return ''
    # Collapse IN-lists first — `IN (1,2,3)` vs `IN (4,5)` would otherwise
    # produce different fingerprints. Both are "same fundamental query".
    s = _IN_LIST.sub('IN (?)', sql)
    s = _PARAM_PLACEHOLDERS.sub('?', s)
    s = _WHITESPACE.sub(' ', s).strip().lower()
    return s[:200]


# ─── Detection ────────────────────────────────────────────────────────────

class _Detector:
    """Per-request detector state. Created fresh by the middleware on
    each request; the query-audit hook reaches into ``_local`` to find
    it.
    """
    __slots__ = ('threshold', 'counts', 'first_seen_at')

    def __init__(self, threshold: int = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self.counts: dict[str, int] = {}
        # First fingerprint seen at this index (rough proxy for traceback
        # location — we don't capture stack at query time because it's
        # expensive)
        self.first_seen_at: dict[str, int] = {}

    def record(self, sql: str, query_index: int):
        fp = fingerprint_sql(sql)
        if not fp:
            return
        if fp not in self.counts:
            self.counts[fp] = 1
            self.first_seen_at[fp] = query_index
        else:
            self.counts[fp] += 1

    def findings(self) -> list[dict]:
        """Templates that ran > threshold times. Sorted by count desc."""
        out = []
        for fp, n in self.counts.items():
            if n >= self.threshold:
                out.append({
                    'fingerprint': fp,
                    'count': n,
                    'first_seen_at_query': self.first_seen_at[fp],
                })
        out.sort(key=lambda x: -x['count'])
        return out


# Public helper for the query_audit hook to call.
def record_query(sql: str, query_index: int) -> None:
    det = getattr(_local, 'detector', None)
    if det is not None:
        det.record(sql, query_index)


# ─── Middleware ───────────────────────────────────────────────────────────

class NPlusOneMiddleware:
    """Wires the detector into per-request state.

    Must run INSIDE QueryAuditMiddleware (which sets _local.state for
    the connection.execute_wrapper hook). MIDDLEWARE ordering:

        ...
        'apps.telemetry.query_audit.QueryAuditMiddleware',
        'apps.telemetry.n_plus_one.NPlusOneMiddleware',
        ...

    On the way out, surfaces findings via:
      • WARN log line per detected N+1 fingerprint
      • response['X-N-Plus-One'] header in DEBUG (count, top template)
      • optional raise via DB_QUERY_BUDGET_STRICT (for CI)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold = int(getattr(settings, 'N_PLUS_ONE_THRESHOLD',
                                      DEFAULT_THRESHOLD))
        self.strict = bool(getattr(settings, 'DB_QUERY_BUDGET_STRICT', False))

    def __call__(self, request):
        # Skip non-API + metrics paths
        if request.path.startswith('/metrics'):
            return self.get_response(request)

        detector = _Detector(threshold=self.threshold)
        _local.detector = detector
        # Track query index by intercepting the query_audit count
        try:
            # We don't have direct access to query_audit's counter, so
            # we use a local index that the wrap hook bumps.
            _local.query_index = 0
        except Exception:
            pass

        # Install our own execute wrapper for fingerprinting. The
        # query_audit wrapper handles counting; we just observe the SQL.
        def _on_query(execute, sql, params, many, context):
            try:
                _local.query_index += 1
                detector.record(sql or '', _local.query_index)
            except Exception:
                pass
            return execute(sql, params, many, context)

        try:
            with connection.execute_wrapper(_on_query):
                response = self.get_response(request)
        finally:
            _local.detector = None
            _local.query_index = 0

        # Post-flight: surface findings
        findings = detector.findings()
        view_budget = self._view_budget(request)
        total_queries = int(getattr(request, '_db_queries', 0) or 0)

        if findings:
            for f in findings[:5]:
                log.warning(
                    'n_plus_one: %s ran %d times on %s %s '
                    '(first at query #%d)',
                    f['fingerprint'][:140], f['count'],
                    request.method, request.path,
                    f['first_seen_at_query'],
                )

        # Per-view budget check
        if view_budget is not None and total_queries > view_budget:
            msg = (
                f'db_query_budget exceeded for {request.method} {request.path}: '
                f'{total_queries} > {view_budget}'
            )
            if self.strict:
                # In CI we want hard fail on regression
                raise DBQueryBudgetExceeded(msg)
            log.warning(msg)

        if settings.DEBUG and findings:
            try:
                top = findings[0]
                response['X-N-Plus-One'] = (
                    f'{len(findings)} templates; '
                    f'top: {top["count"]}× "{top["fingerprint"][:80]}"'
                )
            except Exception:
                pass

        return response

    @staticmethod
    def _view_budget(request) -> Optional[int]:
        """Read ``db_query_budget`` from the resolved view, if any.

        Supports both class-based views (attribute on the class) and
        function-based views (attribute on the function).
        """
        try:
            match = getattr(request, 'resolver_match', None)
            if match is None:
                return None
            func = match.func
            # CBVs expose .cls; DRF APIView too
            cls = getattr(func, 'cls', None) or getattr(func, 'view_class', None)
            if cls is not None:
                return getattr(cls, 'db_query_budget', None)
            return getattr(func, 'db_query_budget', None)
        except Exception:
            return None


class DBQueryBudgetExceeded(Exception):
    """Raised in strict mode (CI) when a view exceeds its declared
    db_query_budget. Production logs the same condition as WARN and
    serves the response normally — we never half-deny a query result
    over an observability concern."""


# ─── Test helper ──────────────────────────────────────────────────────────

@contextmanager
def assert_query_count(*, max: int,
                        n_plus_one_threshold: int = DEFAULT_THRESHOLD):
    """Test fixture context manager.

    Usage in pytest:

        with assert_query_count(max=10):
            client.get('/api/v1/products/')

    Asserts that:
      • The block's total DB query count is <= ``max``.
      • No SQL template ran more than ``n_plus_one_threshold`` times.

    Counts ALL queries against the default connection — not scoped to
    a specific view. Combine with a single request inside the block.
    """
    import django.db
    counter = {'count': 0, 'templates': {}}

    def _wrapper(execute, sql, params, many, context):
        counter['count'] += 1
        fp = fingerprint_sql(sql or '')
        if fp:
            counter['templates'][fp] = counter['templates'].get(fp, 0) + 1
        return execute(sql, params, many, context)

    with django.db.connection.execute_wrapper(_wrapper):
        yield counter

    if counter['count'] > max:
        raise AssertionError(
            f'Query count {counter["count"]} exceeded max={max}. '
            f'Top templates: '
            f'{sorted(counter["templates"].items(), key=lambda x: -x[1])[:5]}'
        )

    n_plus_one = [
        (fp, n) for fp, n in counter['templates'].items()
        if n >= n_plus_one_threshold
    ]
    if n_plus_one:
        raise AssertionError(
            f'N+1 detected (threshold={n_plus_one_threshold}). '
            f'Templates: {n_plus_one[:5]}'
        )
