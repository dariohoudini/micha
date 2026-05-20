"""
middleware/rate_limiter.py
───────────────────────────

Edge-level per-IP rate limiter that composes with DRF throttles.

Why this exists alongside DRF throttles
────────────────────────────────────────
DRF throttling lives in the VIEW dispatch layer — it's applied per
view class, and the request has already passed authentication,
content negotiation, etc. by the time the throttle fires. Two real
gaps that DRF throttles don't cover:

  1. A flood of unauthenticated requests against MIXED endpoints (some
     throttled, some not) burns server CPU even if eventually rejected.
     A burst of 10k req/s saturates pods before throttling kicks in
     for traffic targeted at unthrottled paths.

  2. DRF's UserRateThrottle / AnonRateThrottle don't track 429 history.
     An attacker who hits the throttle just gets 429s indefinitely;
     nothing escalates them. At scale (1M+ users) you want repeat
     offenders to get a SHORT BAN — cheaper to refuse outright than to
     run the throttle check on every request.

This middleware sits in the MIDDLEWARE chain BEFORE DRF, with a
two-band sliding-window check + an auto-ban on repeat 429 offenders:

  • Burst band:   anon_burst limit, 1-minute window
  • Sustained:    anon_sustained limit, 1-hour window
  • Ban escalation: after N 429s within ban-window, IP gets banned for
    ban-duration. Banned IPs short-circuit to 429 BEFORE any band check
    (cheap rejection — single cache lookup).

The bands use the rates set in REST_FRAMEWORK.DEFAULT_THROTTLE_RATES
('anon_burst', 'anon_sustained') so ops tune one place for both
middleware + DRF.

Trusted-proxy XFF handling
───────────────────────────
``X-Forwarded-For`` is honoured ONLY when the immediate REMOTE_ADDR is
in ``settings.TRUSTED_PROXY_IPS``. Without this guard, a client can
send ``X-Forwarded-For: 1.2.3.4`` and look like it's coming from any
IP — defeating the rate limit entirely. The codebase has a dozen
places that blindly trust XFF for client_ip extraction; the rate
limiter MUST get this right because it's the security boundary, so
we don't reuse those helpers here.

Skip-paths
───────────
``RATE_LIMITER_SKIP_PATHS`` (default: ``/health/``, ``/metrics``) opt
out of rate limiting entirely. Health probes from the load balancer
shouldn't count against the band.

Public API
──────────
This is a middleware class. Configure via settings:

  MIDDLEWARE = [
      ...
      'middleware.rate_limiter.EdgeRateLimiterMiddleware',
      ...   # AFTER request-id middleware, BEFORE DRF view dispatch
  ]
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


log = logging.getLogger(__name__)


_RATE_RE = re.compile(r'^(\d+)\s*/\s*(second|minute|hour|day)$', re.IGNORECASE)
_PERIOD_SECONDS = {
    'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400,
}


def _parse_rate(rate_str: str) -> tuple[int, int]:
    """'30/minute' -> (30, 60). Returns (0, 0) if unparseable."""
    if not rate_str:
        return 0, 0
    m = _RATE_RE.match(rate_str)
    if not m:
        return 0, 0
    return int(m.group(1)), _PERIOD_SECONDS[m.group(2).lower()]


def _setting(name, default):
    return getattr(settings, name, default)


def _band_rates() -> dict:
    """Read burst + sustained rates from DRF's throttle table so ops
    has ONE config source for both layers."""
    rates = (
        getattr(settings, 'REST_FRAMEWORK', {})
        .get('DEFAULT_THROTTLE_RATES', {})
    )
    return {
        'burst': _parse_rate(rates.get('anon_burst', '30/minute')),
        'sustained': _parse_rate(rates.get('anon_sustained', '200/hour')),
    }


def _skip_paths() -> set:
    return set(_setting('RATE_LIMITER_SKIP_PATHS', ['/health/', '/metrics']) or [])


def _ban_threshold() -> int:
    return int(_setting('RATE_LIMITER_BAN_THRESHOLD', 5))


def _ban_threshold_window() -> int:
    return int(_setting('RATE_LIMITER_BAN_THRESHOLD_WINDOW', 60))


def _ban_duration() -> int:
    return int(_setting('RATE_LIMITER_BAN_DURATION', 600))


def _disabled() -> bool:
    return not bool(_setting('RATE_LIMITER_ENABLED', True))


def _client_ip(request) -> str:
    """Resolve client IP with trusted-proxy XFF — delegates to the
    canonical ``middleware.client_ip.get_client_ip`` helper.

    Rate limiting IS a security boundary, so ``trusted_only=True``:
    XFF is honoured ONLY if REMOTE_ADDR is in TRUSTED_PROXY_IPS. A
    direct client sending an arbitrary X-Forwarded-For header gets
    its REMOTE_ADDR returned instead — the spoof is defeated at this
    layer.
    """
    from middleware.client_ip import get_client_ip
    return get_client_ip(request, trusted_only=True)


def _sliding_window_count(key: str, window_seconds: int, now: float) -> int:
    """Atomic-ish sliding window via Redis sorted sets.

    Falls back to a fixed-window counter if the cache backend doesn't
    expose ZADD / ZCOUNT (LocMem doesn't). The fallback is less precise
    near window boundaries but is still bounded by the band limit.

    Returns the count of requests in the past ``window_seconds``
    INCLUDING the one we just recorded.
    """
    try:
        client = cache.client.get_client(write=True)  # type: ignore[attr-defined]
        # Sorted-set window. Score = timestamp, member = unique tick.
        member = f'{now:.6f}-{int(now * 1_000_000) % 1_000_000}'
        cutoff = now - window_seconds
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds + 5)
        _, _, count, _ = pipe.execute()
        return int(count)
    except Exception:
        # LocMem / single-process fallback.
        bucket_key = f'{key}:bucket'
        bucket = int(now // window_seconds)
        full_key = f'{bucket_key}:{bucket}'
        try:
            new_val = cache.incr(full_key)
        except ValueError:
            cache.set(full_key, 1, timeout=window_seconds + 5)
            new_val = 1
        return int(new_val)


def _is_banned(ip: str) -> bool:
    return bool(cache.get(f'edge_ban:{ip}'))


def _ban(ip: str, duration: int):
    cache.set(f'edge_ban:{ip}', 1, timeout=duration)
    log.warning(
        'edge_rate_limiter.ban',
        extra={'ip': ip, 'duration_seconds': duration},
    )


def _bump_reject_counter(ip: str) -> int:
    """Track 429-rejection density for ban escalation."""
    key = f'edge_429:{ip}:{int(time.time() // _ban_threshold_window())}'
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, 1, timeout=_ban_threshold_window() + 5)
        return 1


def _is_skipped(path: str) -> bool:
    for p in _skip_paths():
        if path.startswith(p):
            return True
    return False


def _too_many_response(retry_after: int, reason: str) -> JsonResponse:
    resp = JsonResponse(
        {'error': 'rate_limited', 'detail': reason, 'retry_after': retry_after},
        status=429,
    )
    # RFC 6585 — Retry-After header is the standard hint to clients.
    resp['Retry-After'] = str(retry_after)
    return resp


class EdgeRateLimiterMiddleware:
    """Per-IP burst + sustained rate limiter with auto-ban escalation.

    Inserted BEFORE DRF in the MIDDLEWARE chain. Refuses banned IPs
    cheaply; counts requests per IP across burst (60s) + sustained (1h)
    windows; auto-bans IPs that produce > N 429s within a short window.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _disabled():
            return self.get_response(request)

        path = request.path or ''
        if _is_skipped(path):
            return self.get_response(request)

        ip = _client_ip(request)
        if not ip:
            # No IP — can't enforce. Pass through (this shouldn't happen
            # behind a real load balancer).
            return self.get_response(request)

        # Ban cache check — cheapest exit.
        if _is_banned(ip):
            return _too_many_response(
                retry_after=60,
                reason='ip_temporarily_banned',
            )

        bands = _band_rates()
        now = time.monotonic_ns() / 1_000_000_000  # high-res monotonic

        burst_limit, burst_window = bands['burst']
        if burst_limit and burst_window:
            count = _sliding_window_count(
                f'edge_burst:{ip}', burst_window, now,
            )
            if count > burst_limit:
                rejects = _bump_reject_counter(ip)
                if rejects >= _ban_threshold():
                    _ban(ip, _ban_duration())
                return _too_many_response(
                    retry_after=burst_window,
                    reason='burst_rate_exceeded',
                )

        sustained_limit, sustained_window = bands['sustained']
        if sustained_limit and sustained_window:
            count = _sliding_window_count(
                f'edge_sustained:{ip}', sustained_window, now,
            )
            if count > sustained_limit:
                rejects = _bump_reject_counter(ip)
                if rejects >= _ban_threshold():
                    _ban(ip, _ban_duration())
                return _too_many_response(
                    retry_after=sustained_window,
                    reason='sustained_rate_exceeded',
                )

        return self.get_response(request)
