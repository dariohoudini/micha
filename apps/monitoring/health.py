"""
apps/monitoring/health.py

Split health check endpoints:

  /healthz — LIVENESS. Process is running. Zero dependencies. Returns 200
             unless the WSGI stack itself is broken. Used by k8s
             livenessProbe — failing this kills+restarts the pod.

  /readyz  — READINESS. Process is willing AND able to serve traffic.
             Probes DB (hard — required to serve) and cache / celery
             broker / celery workers (soft — degraded mode but still
             ready). Used by k8s readinessProbe — failing this deloads
             the pod from the service endpoints but DOES NOT restart it.

Why split? The legacy /health/ conflates these and fails-closed on DB.
Result: a 2-second DB blip → k8s sees liveness fail → kills the pod →
new pod tries to connect to the same blipped DB → fails → restart loop
→ amplifies the incident into an outage instead of riding through it.

Liveness should only fail when restart is the right remediation
(process wedged, deadlock, OOM coming). Readiness can fail freely.
"""
from __future__ import annotations

import time
import logging

from django.views.decorators.http import require_GET
from django.http import JsonResponse


log = logging.getLogger(__name__)


@require_GET
def healthz(request):
    """Liveness — no deps, always 200 unless the WSGI stack is broken."""
    return JsonResponse({'status': 'alive'}, status=200)


@require_GET
def build_info(request):
    """Version visibility (CI/CD & VC doc CH13/CH20).

    Answers "what code is running in prod right now?" — essential for
    incident response. The CI pipeline stamps the image with the commit
    SHA, semantic version, and build timestamp (image labels / build args,
    CH12-13) and the deploy injects them as env vars; this endpoint surfaces
    them. Falls back to safe placeholders in dev where they aren't set.

    No dependencies, no auth — it's operational metadata (no secrets).
    """
    import os

    from django.conf import settings

    settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings')
    environment = ('development' if getattr(settings, 'DEBUG', False)
                   else os.environ.get('MICHA_ENV', 'production'))
    return JsonResponse({
        'service': 'micha-backend',
        'version': os.environ.get('APP_VERSION', 'dev'),
        'commit': os.environ.get('GIT_SHA', os.environ.get('GIT_COMMIT', 'unknown')),
        'build_time': os.environ.get('BUILD_TIME', 'unknown'),
        'settings_module': settings_module,
        'environment': environment,
    }, status=200)


@require_GET
def readyz(request):
    """Readiness — DB hard (must work to serve), cache/redis/celery soft.

    Returns 200 with 'ok' or 'degraded' depending on soft checks.
    Returns 503 only when a HARD dependency is unhealthy.
    """
    checks = {}
    hard_ok = True

    # ── DB (hard) ─────────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        from django.db import connection
        connection.ensure_connection()
        with connection.cursor() as c:
            c.execute('SELECT 1')
            c.fetchone()
        checks['database'] = {
            'status': 'ok',
            'latency_ms': round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as e:
        hard_ok = False
        checks['database'] = {'status': 'error', 'detail': str(e)[:200]}
        log.error('readyz: DB check failed: %s', e)

    # ── Cache (soft) ──────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        from django.core.cache import cache
        cache.set('_readyz_probe', '1', timeout=5)
        ok = cache.get('_readyz_probe') == '1'
        cache.delete('_readyz_probe')
        checks['cache'] = {
            'status': 'ok' if ok else 'degraded',
            'latency_ms': round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as e:
        checks['cache'] = {'status': 'unavailable', 'detail': str(e)[:200]}

    # ── Celery broker (soft) ──────────────────────────────────────────
    try:
        from django.conf import settings
        import redis as redis_lib
        url = getattr(settings, 'REDIS_URL',
                      getattr(settings, 'CELERY_BROKER_URL',
                              'redis://localhost:6379/0'))
        r = redis_lib.from_url(url, socket_connect_timeout=1,
                               socket_timeout=1)
        r.ping()
        checks['celery_broker'] = {'status': 'ok'}
    except Exception as e:
        checks['celery_broker'] = {'status': 'unavailable',
                                   'detail': str(e)[:200]}

    # ── Celery workers (soft, BEST EFFORT) ────────────────────────────
    # ``inspect()`` is expensive and timing-sensitive — short timeout,
    # never fail the probe over it.
    try:
        from config.celery import app as celery_app
        i = celery_app.control.inspect(timeout=0.5)
        active = i.active() or {}
        checks['celery_workers'] = {
            'status': 'ok' if active else 'no_workers',
            'count': len(active),
        }
    except Exception as e:
        checks['celery_workers'] = {'status': 'unavailable',
                                    'detail': str(e)[:200]}

    body = {
        'status': 'ok' if hard_ok else 'unready',
        'checks': checks,
    }
    return JsonResponse(body, status=200 if hard_ok else 503)
