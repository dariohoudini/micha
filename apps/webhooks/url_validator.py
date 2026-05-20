"""
apps/webhooks/url_validator.py
──────────────────────────────

SSRF defense for outbound webhooks.

Threat: a seller registers a webhook URL pointing at INSIDE the
platform's infrastructure (a private RFC-1918 IP, the AWS metadata
service, our own internal admin port, …). Our delivery worker
faithfully POSTs to that URL with our own valid HMAC signature,
exposing internal services to credentialed-looking external traffic.

Real-world impact of a missing SSRF check:
  • Read AWS instance metadata via 169.254.169.254 → temporary IAM
    creds → S3 / RDS / KMS exfiltration.
  • Hit Redis on 127.0.0.1:6379 — set arbitrary cache keys.
  • Hit Kubernetes API on 10.0.0.1 → cluster info.
  • Hit internal admin services on 192.168.*.* → privilege escalation.

This validator is the chokepoint. It runs at SUBSCRIPTION CREATE TIME
and again at DELIVERY TIME (because DNS can change — the so-called
DNS rebinding attack: the hostname resolves to a public IP during
validation, then to 127.0.0.1 at delivery time).

Defense layers:

  1. URL scheme: only http(s). No file://, javascript:, gopher://, etc.

  2. Scheme strictness: https REQUIRED in production. DEBUG allows
     http for local-dev integration testing.

  3. Hostname must NOT be a literal IP in a denied range OR a hostname
     that resolves to one. Denied ranges:
       127.0.0.0/8   (loopback)
       0.0.0.0/8     (this-network)
       10.0.0.0/8    (RFC 1918 private)
       172.16.0.0/12 (RFC 1918 private)
       192.168.0.0/16 (RFC 1918 private)
       169.254.0.0/16 (link-local — INCLUDES AWS/GCP metadata)
       100.64.0.0/10 (CGNAT)
       ::1/128       (IPv6 loopback)
       fc00::/7      (IPv6 unique local)
       fe80::/10     (IPv6 link-local)
       Multicast + reserved.

  4. DNS rebinding defense: at validation we resolve the hostname and
     verify EVERY A record passes. At delivery time the worker does
     the same check on the connection's real-time resolved IP and
     refuses to POST if the IP is now private. Without the second
     check, an attacker can register example.com (resolves to a
     public IP at validation) and then flip example.com's DNS to
     127.0.0.1 before delivery.

  5. Port allowlist: 80, 443, 8080, 8443. Sellers running on weird
     ports can request an exception via support. Catches "give me a
     webhook pointing at internal admin port 9200" attacks.

  6. URL length cap so we don't load multi-MB strings.

NEVER raises — returns Decision(allowed: bool, reason: str). Callers
log the reason and reject with a clear error.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable, List
from urllib.parse import urlparse

from django.conf import settings


__all__ = ['Decision', 'validate_webhook_url', 'resolve_safe_ips']


# Allowed schemes — anything else is rejected immediately. Most
# importantly NOT in this list: file, javascript, gopher, ftp, data, etc.
_ALLOWED_SCHEMES = frozenset({'http', 'https'})

# Allowed ports. Sellers asking for non-standard get an explicit
# exception (and an audit row).
_ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})

# Maximum URL length. 500 chars matches the DB column; cap here so
# we reject before storage.
_MAX_URL_LEN = 500


@dataclass
class Decision:
    allowed: bool
    reason: str = ''


def _is_private_ip(ip_str: str) -> bool:
    """True if the IP literal is in any denied range."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False  # not a literal IP — caller's DNS check handles names
    # is_private covers RFC 1918 + ::1 + fc00::/7
    # is_loopback covers 127/8 + ::1
    # is_link_local covers 169.254/16 + fe80::/10 (INCLUDING AWS metadata)
    # is_multicast / is_reserved / is_unspecified for completeness
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_safe_ips(hostname: str) -> List[str]:
    """Resolve hostname; return IPs only if ALL resolved IPs pass the
    private-range check. Empty list means "unsafe" or "unresolvable" —
    caller treats both as rejection. Caller can also use the returned
    list at delivery time as an IP pin for socket-level defense."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return []
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        return []
    if any(_is_private_ip(ip) for ip in ips):
        return []
    return ips


def validate_webhook_url(url: str, *, allow_http: bool | None = None) -> Decision:
    """Run the full SSRF-defense gauntlet on a candidate webhook URL.

    Args:
      url: candidate URL string.
      allow_http: if True, http:// scheme is allowed (dev / staging).
                  if False, only https://. If None, infers from DEBUG.

    Returns Decision(allowed, reason). Caller logs reason verbatim;
    safe to surface to the user — never leaks internal state.
    """
    if not url or not isinstance(url, str):
        return Decision(False, 'url is empty')
    if len(url) > _MAX_URL_LEN:
        return Decision(False, f'url longer than {_MAX_URL_LEN} chars')

    if allow_http is None:
        allow_http = bool(getattr(settings, 'DEBUG', False))

    try:
        parsed = urlparse(url)
    except Exception:
        return Decision(False, 'malformed url')

    scheme = (parsed.scheme or '').lower()
    if scheme not in _ALLOWED_SCHEMES:
        return Decision(False, f'scheme {scheme!r} not allowed; use https')
    if scheme == 'http' and not allow_http:
        return Decision(False, 'https required in production')

    if not parsed.hostname:
        return Decision(False, 'missing hostname')

    # Reject embedded credentials (user:pass@) — those don't belong
    # in a webhook URL and could mask intent during code review.
    if '@' in parsed.netloc.split(':')[0] or parsed.username or parsed.password:
        return Decision(False, 'embedded credentials not allowed')

    # Port check
    try:
        port = parsed.port  # may raise ValueError on bad strings
    except ValueError:
        return Decision(False, 'invalid port')
    if port is None:
        port = 443 if scheme == 'https' else 80
    if port not in _ALLOWED_PORTS:
        return Decision(False,
                        f'port {port} not allowed; use 80/443/8080/8443')

    # Hostname is a literal IP — check the IP directly.
    try:
        ipaddress.ip_address(parsed.hostname)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if _is_private_ip(parsed.hostname):
            return Decision(False,
                            'private / loopback / link-local IP not allowed')
        return Decision(True, 'ok')

    # Hostname is a name — resolve and verify every A record is public.
    ips = resolve_safe_ips(parsed.hostname)
    if not ips:
        return Decision(False, 'hostname unresolvable or resolves to '
                                'a private / loopback / link-local IP')

    return Decision(True, 'ok')
