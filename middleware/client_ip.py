"""
middleware/client_ip.py
────────────────────────

Single canonical helper for resolving the client IP from a request.

Why this exists
────────────────
The codebase had ~18 places that read ``request.META['HTTP_X_FORWARDED_FOR']``
directly. ALL of them blindly trusted the header. Any direct client can
send ``X-Forwarded-For: 1.2.3.4`` and be seen by the server as coming
from 1.2.3.4 — defeating any per-IP guard built on top.

This wasn't just a hypothetical. Three security-grade call sites were
broken in production:

  • Inbound webhook IP allowlist (commit 42ac254). I added a per-
    provider IP allowlist as defence-in-depth and routed it through
    the existing ``_client_ip()`` helper that blindly trusted XFF —
    an attacker who knew the signing secret could ALSO spoof XFF to
    claim a whitelisted IP. The defence layer was decorative.

  • Fraud-signal capture (apps/security/fraud_signals.py,
    fraud_engine.py). "Impossible travel" detection compares the IPs
    of consecutive logins. If XFF is spoofable, an attacker can fake
    the geography of EVERY login from one machine, defeating the
    signal entirely.

  • Two-factor enrolment IP capture
    (apps/two_factor/views.py). The IP saved at enrolment time is
    later used for "new device" detection on subsequent logins. Spoof
    XFF at enrolment, every real login looks like a "new device" and
    the alerting drowns in noise.

The fix: a single ``get_client_ip(request, trusted_only=False)``
helper. When ``trusted_only=True``, XFF is honoured ONLY if
``REMOTE_ADDR ∈ settings.TRUSTED_PROXY_IPS``. Otherwise
``REMOTE_ADDR`` is returned directly — defeating the spoof.

When to pass ``trusted_only=True``
───────────────────────────────────
ALWAYS, for any path where IP is a SECURITY boundary:
  • Per-IP rate limit / lockout / ban
  • Webhook IP allowlist
  • Fraud signal capture
  • New-device detection IP
  • Any IP that influences AUTH decisions

The non-strict mode (default ``trusted_only=False``) preserves
back-compat for logging / audit / analytics call sites where a
spoofed XFF is still useful as a forensic signal even if not
authoritative. (A forensic row that records "claimed IP 1.2.3.4
from REMOTE 5.6.7.8" is more useful than one that records 5.6.7.8
alone.)

Settings
─────────
  TRUSTED_PROXY_IPS = ['10.0.0.5', '10.0.0.6']
      The actual REMOTE_ADDR values your reverse proxy presents to
      the app. Empty in dev (REMOTE_ADDR is the real client). Populate
      from the load-balancer / CDN egress IPs in prod.
"""
from __future__ import annotations

from typing import Optional


def _trusted_proxies() -> set:
    try:
        from django.conf import settings
        return set(getattr(settings, 'TRUSTED_PROXY_IPS', []) or [])
    except Exception:
        return set()


def get_client_ip(request, *, trusted_only: bool = False) -> str:
    """Resolve the client IP from a request.

    Args:
      request: a Django/DRF request. Must have ``.META``.
      trusted_only: when True, XFF is honoured ONLY if REMOTE_ADDR is
        in ``settings.TRUSTED_PROXY_IPS``. Pass True for any path that
        treats IP as a security boundary. Default False for back-compat
        with audit/log/analytics call sites.

    Returns:
      The IP string (truncated to 45 chars to fit GenericIPAddressField).
      Empty string when no IP can be determined.
    """
    remote = (request.META.get('REMOTE_ADDR') or '').strip()
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()

    if not xff:
        return remote[:45]

    # XFF present. In strict mode, only honour if proxy is trusted.
    if trusted_only:
        if remote in _trusted_proxies():
            return xff.split(',')[0].strip()[:45]
        # Untrusted source claiming to be behind a proxy — IGNORE XFF.
        return remote[:45]

    # Lenient mode: honour XFF leftmost (back-compat behaviour). Useful
    # for forensic logging even when not authoritative.
    return xff.split(',')[0].strip()[:45]
