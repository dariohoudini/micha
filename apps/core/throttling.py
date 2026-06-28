"""
apps/core/throttling.py — fail-open / fail-closed rate-limit bases.

Rate Limiting & Abuse Control doc, Part 1 CH2 (principle 3), CH11, CH14:

  "FAIL OPEN FOR AVAILABILITY, FAIL CLOSED FOR SECURITY: if the rate-limit
   store (Redis) is unavailable, GENERAL traffic should fail OPEN (do not
   take the whole site down because the limiter blinked) — BUT
   security-critical limits (login, OTP, money) fail CLOSED (deny if you
   cannot verify the count) because the cost of letting abuse through there
   is too high."

DRF's stock throttles do neither deliberately: when the cache backend
raises (Redis down), ``SimpleRateThrottle.allow_request`` propagates the
error → a 500, or — if the cache silently swallows errors — it reads an
empty history and ALLOWS unlimited requests (fails OPEN on login/OTP/money,
a brute-force / OTP-flood / payment-spam window during a Redis blip).

These bases make the fail behaviour an explicit, per-throttle decision:
  * FailOpen*   — store error → ALLOW (availability). General reads/writes.
  * FailClosed* — store error → DENY 429 (security). Login / OTP / payment.
"""
import logging

from rest_framework.exceptions import Throttled
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger('micha')

# Retry-After (seconds) returned when we deny because the store is down.
_STORE_DOWN_RETRY_AFTER = 30


class _FailModeMixin:
    """Wrap allow_request so a counter-store failure resolves to an explicit
    fail-open (allow) or fail-closed (deny) decision instead of a 500 or a
    silent allow. ``fail_open`` is set by the concrete subclass."""

    fail_open = True

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Throttled:
            # Over the limit — let it propagate (this is the normal 429).
            raise
        except Exception as exc:  # cache/Redis unavailable, etc.
            scope = getattr(self, 'scope', self.__class__.__name__)
            logger.warning(
                'rate_limit.store_unavailable',
                extra={'scope': scope, 'fail_open': self.fail_open,
                       'error': str(exc)[:160]},
            )
            if self.fail_open:
                # Availability over strictness for ordinary traffic.
                return True
            # Security-critical: cannot verify the count → DENY (CH11/CH14).
            raise Throttled(wait=_STORE_DOWN_RETRY_AFTER,
                            detail='Rate-limit store unavailable; the request '
                                   'was denied for security. Retry shortly.')


# ── Fail-OPEN (general traffic — availability) ──────────────────────────
class FailOpenAnonRateThrottle(_FailModeMixin, AnonRateThrottle):
    fail_open = True


class FailOpenUserRateThrottle(_FailModeMixin, UserRateThrottle):
    fail_open = True


# ── Fail-CLOSED (login / OTP / money — security) ────────────────────────
class FailClosedAnonRateThrottle(_FailModeMixin, AnonRateThrottle):
    fail_open = False


class FailClosedUserRateThrottle(_FailModeMixin, UserRateThrottle):
    fail_open = False
