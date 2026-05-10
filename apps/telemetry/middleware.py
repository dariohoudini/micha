"""
Per-request latency + count middleware.

Records `micha_http_requests_total` and `micha_http_request_latency_seconds`
with route + method + status labels. Route is the URLconf pattern (e.g.
"/api/v1/orders/<uuid:pk>/") rather than the actual path — keeps cardinality
bounded and dashboards aggregable.

Excludes the /metrics endpoint itself to avoid recording the scrape.
"""
import time

from .metrics import http_requests, http_request_latency

EXCLUDED_PATHS = ('/metrics', '/metrics/', '/healthz')


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path in EXCLUDED_PATHS:
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        elapsed = time.monotonic() - start

        # Bucket the route by URLconf pattern, not raw path, to bound cardinality
        route = self._route_for(request)
        try:
            http_requests.labels(
                method=request.method,
                route=route,
                status=str(response.status_code),
            ).inc()
            http_request_latency.labels(route=route).observe(elapsed)
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
