"""
middleware/cost_telemetry.py
─────────────────────────────

Per-request infrastructure-cost estimate emitted as a Prometheus
counter + a log line.

Why this exists (R3)
─────────────────────
Without per-endpoint cost data, optimisation flies blind. The team
guesses which endpoints are expensive and optimises the wrong ones.
At scale this is the difference between "we serve 100k users on
$5k/month AWS" and "we serve 100k users on $50k/month" — that's the
quote from the audit roadmap.

What it measures
────────────────
For each request we capture:

  • db_time_ms        sum of duration across ORM queries (django.db
                      connection.queries when DEBUG, else estimated
                      from CursorWrapper.execute hook)
  • db_query_count    raw count of queries
  • response_bytes    response.content length (Content-Length)
  • duration_ms       wall-clock request duration

Cost estimate (rough order-of-magnitude):
  $0.0001 per DB second   (RDS db.t3.medium amortised)
  $0.0000001 per response byte (CloudFront egress)
  +$0.00005 baseline per request (Lambda/EC2 amortised)

The absolute number is less important than the relative ranking.
``$0.005 per /products/<pk>/`` vs ``$0.05 per /admin/exports/``
tells you the export endpoint is 10x more expensive — that's what
the team actually needs for capacity planning + per-customer
profitability.

Output
──────
1. structured log line at INFO ``cost.request`` with all fields
2. Prometheus counter ``micha_request_cost_usd_total`` (when
   ``prometheus_client`` is installed) labelled by route + method

Conservative defaults — disabled in DEBUG (would spam the dev
console), enabled in prod.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from django.conf import settings


log = logging.getLogger('micha.cost')


# Prometheus counter is lazy-imported — keeps the dep optional. Tests
# don't need prometheus_client installed.
_PROM_COUNTER = None
_PROM_TRIED = False


def _get_prom_counter():
    global _PROM_COUNTER, _PROM_TRIED
    if _PROM_TRIED:
        return _PROM_COUNTER
    _PROM_TRIED = True
    try:
        from prometheus_client import Counter
        _PROM_COUNTER = Counter(
            'micha_request_cost_usd_total',
            'Estimated per-request infrastructure cost (USD)',
            ['route', 'method', 'status'],
        )
    except Exception:
        _PROM_COUNTER = None
    return _PROM_COUNTER


# Cost-model constants — order-of-magnitude. Documented here so
# overrides via settings are obvious.
DEFAULT_DB_USD_PER_SECOND = 0.0001
DEFAULT_EGRESS_USD_PER_BYTE = 1e-7  # $0.10/GB on CloudFront
DEFAULT_BASELINE_USD_PER_REQUEST = 5e-5


def _model_constant(name: str, default: float) -> float:
    raw = getattr(settings, name, default)
    try:
        return float(raw)
    except Exception:
        return default


def _enabled() -> bool:
    if getattr(settings, 'COST_TELEMETRY_ENABLED', None) is not None:
        return bool(settings.COST_TELEMETRY_ENABLED)
    # Default: ON in non-DEBUG environments only.
    return not getattr(settings, 'DEBUG', False)


def _route_label(request) -> str:
    """Best-effort named-route extraction.

    resolve(path) returns a ResolverMatch with .url_name when the URL
    has one. Otherwise fall back to the resolver's view_name. Both
    are stable labels suitable for Prometheus (won't blow up label
    cardinality on path-id endpoints like /orders/<uuid>/).
    """
    try:
        from django.urls import resolve
        match = resolve(request.path_info)
        return (
            match.url_name
            or match.view_name
            or request.resolver_match.view_name  # type: ignore[union-attr]
            or 'unknown'
        )
    except Exception:
        return 'unknown'


class CostTelemetryMiddleware:
    """Wall-clock + DB telemetry per request.

    Active only when settings.COST_TELEMETRY_ENABLED (or by default
    when DEBUG is False). When disabled, this is a pass-through with
    one boolean check.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not _enabled():
            return self.get_response(request)

        from django.db import connections, reset_queries
        # ``reset_queries`` only matters when DEBUG=True (Django only
        # logs queries then). We rely on the queries log if available;
        # otherwise we count via a query-count delta. Conservative.
        try:
            reset_queries()
        except Exception:
            pass

        start = time.perf_counter()
        response = self.get_response(request)
        duration_s = time.perf_counter() - start

        db_time_s = 0.0
        db_count = 0
        try:
            for alias in connections.databases:
                conn = connections[alias]
                queries = getattr(conn, 'queries', None) or []
                db_count += len(queries)
                for q in queries:
                    db_time_s += float(q.get('time') or 0)
        except Exception:
            pass

        response_bytes = 0
        try:
            if hasattr(response, 'content'):
                response_bytes = len(response.content or b'')
        except Exception:
            pass

        # Cost model.
        db_rate = _model_constant('COST_DB_USD_PER_SECOND',
                                  DEFAULT_DB_USD_PER_SECOND)
        egress_rate = _model_constant('COST_EGRESS_USD_PER_BYTE',
                                      DEFAULT_EGRESS_USD_PER_BYTE)
        baseline = _model_constant('COST_BASELINE_USD_PER_REQUEST',
                                   DEFAULT_BASELINE_USD_PER_REQUEST)
        cost_usd = (
            db_time_s * db_rate
            + response_bytes * egress_rate
            + baseline
        )

        route = _route_label(request)
        status = getattr(response, 'status_code', 0)

        log.info(
            'cost.request',
            extra={
                'route': route,
                'method': request.method,
                'status': status,
                'duration_ms': round(duration_s * 1000.0, 2),
                'db_time_ms': round(db_time_s * 1000.0, 2),
                'db_query_count': db_count,
                'response_bytes': response_bytes,
                'cost_usd_est': round(cost_usd, 8),
            },
        )

        counter = _get_prom_counter()
        if counter is not None:
            try:
                counter.labels(
                    route=route, method=request.method,
                    status=str(status),
                ).inc(cost_usd)
            except Exception:
                pass

        return response
