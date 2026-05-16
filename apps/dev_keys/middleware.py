"""
apps/dev_keys/middleware.py

Logs one APIKeyUsage row per request that authenticated via an API key.
Adds the row at response time so we capture status + latency. Never blocks
the response on log failure.
"""
import logging
import time

from .models import APIKeyUsage

log = logging.getLogger(__name__)


class APIKeyUsageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        try:
            key = getattr(request, '_api_key', None)
            if key is not None:
                self._log(key, request, response, start)
        except Exception:
            # NEVER break the response over a logging failure
            log.debug('APIKeyUsage write failed', exc_info=True)
        return response

    def _log(self, key, request, response, start):
        latency_ms = int((time.monotonic() - start) * 1000)
        path = request.path[:300]
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:200]
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = (xff.split(',')[0].strip() if xff else (request.META.get('REMOTE_ADDR') or ''))[:45]
        error = ''
        if response.status_code >= 400:
            # Capture error type from body if it's JSON
            try:
                content = response.content[:300].decode('utf-8', errors='replace')
                error = content[:200]
            except Exception:
                pass
        APIKeyUsage.objects.create(
            key=key, method=request.method[:8], path=path,
            status=response.status_code, latency_ms=latency_ms,
            ip=ip or None, user_agent=ua, error=error,
        )
