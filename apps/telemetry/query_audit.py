"""
Query-count audit middleware.

Goal: catch N+1 query explosions before they become latency issues in
production. Pairs with the telemetry stack — counts go to a Prometheus
histogram and a structured warning log when a single request runs more
than `WARN_THRESHOLD` queries.

How it works
------------
django.db.connection.queries is populated only when DEBUG=True. To work
in production we hook our own counter via the queries-executed signal
on every connection, which doesn't cost anything when nothing watches.

In dev, tail the log for warnings like:
   WARNING q-audit: GET /api/v1/products/ ran 42 queries (threshold 25)

The middleware also exposes the count on response headers in DEBUG so
you can spot regressions in browser devtools:
   X-DB-Queries: 4
"""
import logging
import threading

from django.conf import settings
from django.db import connection

logger = logging.getLogger('q-audit')

WARN_THRESHOLD = 25       # log a warning above this
SLOW_QUERY_MS = 50        # log individual slow queries

# Per-thread counter (Django runs requests in worker threads).
_local = threading.local()


def _on_query_executed(execute, sql, params, many, context):
    """django.db.backends.utils.CursorDebugWrapper hook.

    We use the public execute_wrapper API so we count queries even when
    DEBUG=False — connection.queries is empty in that mode.
    """
    state = getattr(_local, 'state', None)
    if state is None:
        return execute(sql, params, many, context)

    import time
    t0 = time.monotonic()
    try:
        return execute(sql, params, many, context)
    finally:
        dt_ms = (time.monotonic() - t0) * 1000.0
        state['count'] += 1
        state['ms_total'] += dt_ms
        if dt_ms >= SLOW_QUERY_MS:
            # Compress sql to a single line for log digestibility
            sql_one = ' '.join((sql or '').split())[:200]
            state['slow_queries'].append((dt_ms, sql_one))


class QueryAuditMiddleware:
    """Counts DB queries per HTTP request. Logs warnings on N+1 risk."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip the metrics endpoint — it triggers gauge refreshes that we
        # don't want to count as "request" queries.
        if request.path.startswith('/metrics'):
            return self.get_response(request)

        state = {'count': 0, 'ms_total': 0.0, 'slow_queries': []}
        _local.state = state

        with connection.execute_wrapper(_on_query_executed):
            response = self.get_response(request)

        _local.state = None

        # Telemetry counter (best-effort)
        try:
            from .metrics import http_db_queries
            route = self._route_for(request)
            http_db_queries.labels(route=route).observe(state['count'])
        except Exception:
            pass

        # Warn-on-threshold
        if state['count'] >= WARN_THRESHOLD:
            extra = {
                'count': state['count'],
                'ms_total': round(state['ms_total'], 1),
                'slow_queries': len(state['slow_queries']),
                'route': self._route_for(request),
            }
            logger.warning(
                f'{request.method} {request.path} ran {state["count"]} queries '
                f'(threshold {WARN_THRESHOLD}, {state["ms_total"]:.0f}ms in DB)',
                extra=extra,
            )
            for ms, sql in state['slow_queries'][:5]:
                logger.warning(f'  slow ({ms:.0f}ms): {sql}')

        # Surface to browser devtools in DEBUG so devs spot regressions
        if settings.DEBUG:
            try:
                response['X-DB-Queries'] = str(state['count'])
                response['X-DB-MS'] = f'{state["ms_total"]:.0f}'
            except Exception:
                pass
        return response

    @staticmethod
    def _route_for(request) -> str:
        try:
            match = getattr(request, 'resolver_match', None)
            if match and match.route:
                return '/' + match.route.lstrip('^').rstrip('$')
        except Exception:
            pass
        return 'unknown'
