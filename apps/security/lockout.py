"""
apps/security/lockout.py — production-grade brute-force defense.

Two attack vectors covered:

  1. Targeted account attack — repeated guesses against a single email.
     Defense: per-email lockout with exponential backoff.

  2. Credential stuffing — leaked-credential lists hit thousands of
     accounts from one IP / botnet, one or two tries per account so
     per-account lockout never fires.
     Defense: per-IP lockout with a higher threshold.

──────────────────────────────────────────────────────────────────────
Architecture: cache for the hot path, DB for the audit trail
──────────────────────────────────────────────────────────────────────

The login flow runs on every authentication attempt — for a busy
marketplace that's thousands per second under attack. Hitting the DB
to read+write a counter on each attempt makes the auth row a write-
hot lock contention point. So:

  • Hot path (every login): Redis ``cache.incr()`` is atomic across
    workers and adds zero DB load. A failed login increments a
    rolling 15-min counter; when it crosses the threshold, a
    separate ``lock`` key is set with the lockout TTL.

  • Durable path (audit): every attempt also writes a LoginAttempt
    row, asynchronously where possible. If Redis is purged, history
    survives — and we can rebuild the counters from the DB.

  • Source of truth on conflict: cache wins for ``is locked?``
    checks (correctness over completeness — if cache says locked,
    we lock). DB is the forensic record.

──────────────────────────────────────────────────────────────────────
Race safety
──────────────────────────────────────────────────────────────────────

``cache.incr(key)`` is atomic in both Redis and Django's locmem
backend. Concurrent failures from N workers all see strictly
monotonic counter values; exactly one worker observes the threshold
crossing and sets the lock key. The set-lock race (two workers both
observe N=threshold and both call cache.set(lock)) is harmless —
the value being set is identical.

The DB write is NOT in the lockout-decision critical path. It's
fire-and-forget audit; cache state is the gate.

──────────────────────────────────────────────────────────────────────
Anti-enumeration
──────────────────────────────────────────────────────────────────────

Login response shape is identical regardless of:
  • email exists vs doesn't exist
  • password right vs wrong
  • account locked vs not locked (locked → still returns
    invalid_credentials externally; user learns via the
    notification email or via password reset flow)

Timing equalisation: ``equalize_timing()`` runs a dummy password
hash check when the email doesn't exist, so the response time
is indistinguishable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils import timezone


log = logging.getLogger(__name__)


# ── Tunables (override via Django settings if needed) ──────────────────────

# Per-email lockout: graduated severity. Each tier kicks in at its
# threshold and uses that tier's lockout duration. Counter resets on
# successful login or password reset.
EMAIL_LOCKOUT_TIERS = [
    (5,   60 * 15),     # 5 fails → 15-min lock
    (10,  60 * 60),     # 10 fails → 1-hour lock
    (20,  60 * 60 * 24),  # 20 fails → 24-hour lock
]

# Per-IP lockout: defense-in-depth with the upstream per-IP rate limit
# (DEFAULT_THROTTLE_RATES['login'] = '10/minute'). The rate limit absorbs
# the bursty layer; this lockout catches sustained attack.
#
# Threshold tuned so that ~2 minutes of attackers running at the
# throttled rate trips it. A NAT'd household behind one IP shouldn't
# be collaterally locked under realistic patterns: the rolling 15-min
# window is long enough that a real user typing a wrong password
# twice doesn't get near 20.
IP_LOCKOUT_THRESHOLD = 20
IP_LOCKOUT_DURATION_S = 60 * 60  # 1 hour

# Rolling window over which the counters apply. Failures older than
# this don't count toward the threshold.
ATTEMPT_WINDOW_S = 60 * 15  # 15 minutes

# Notification dedupe — don't email a user every retry, just once per hour.
NOTIFICATION_DEDUPE_S = 60 * 60


# ── Public dataclass ──────────────────────────────────────────────────────

@dataclass
class LockoutState:
    """Returned by the gating checks. ``locked`` is the only field
    callers should branch on — the rest is for logging / response
    headers (e.g. Retry-After)."""
    locked: bool
    reason: str = ''
    retry_after_seconds: int = 0


# ── Cache-key helpers ──────────────────────────────────────────────────────

def _norm_email(email: str) -> str:
    return (email or '').strip().lower()


def _email_count_key(email: str) -> str:
    return f'sec:login:fail:email:{_norm_email(email)}'


def _email_lock_key(email: str) -> str:
    return f'sec:login:lock:email:{_norm_email(email)}'


def _ip_count_key(ip: str) -> str:
    return f'sec:login:fail:ip:{ip}'


def _ip_lock_key(ip: str) -> str:
    return f'sec:login:lock:ip:{ip}'


def _notif_dedupe_key(email: str) -> str:
    return f'sec:login:notif:{_norm_email(email)}'


# ── Atomic increment with TTL preservation ────────────────────────────────

def _incr_with_window(key: str, window_s: int) -> int:
    """Atomic incr that also (re)establishes the rolling-window TTL.

    Django's cache.incr() raises ValueError when the key doesn't exist.
    cache.add() is atomic and only succeeds if the key is missing.
    """
    if cache.add(key, 1, timeout=window_s):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # Lost a race between add() and incr() expiring — start fresh.
        cache.set(key, 1, timeout=window_s)
        return 1


# ── Lockout duration policy ────────────────────────────────────────────────

def _duration_for_count(count: int) -> Optional[int]:
    """Map a failure count to a lockout duration in seconds.
    Returns None if the count is below the lowest threshold.
    Walks tiers in descending threshold so higher counts get longer locks."""
    selected = None
    for threshold, duration in EMAIL_LOCKOUT_TIERS:
        if count >= threshold:
            selected = duration
    return selected


# ── Public API ────────────────────────────────────────────────────────────

def check_account_lockout(email: str) -> LockoutState:
    """Cheap pre-auth gate: is this account currently locked?

    Cache-only — never touches the DB. False positives (cache lying)
    are vastly preferable to false negatives, so we trust the cache.
    """
    if not email:
        return LockoutState(locked=False)
    ttl = cache.ttl(_email_lock_key(email)) if hasattr(cache, 'ttl') else None
    locked = cache.get(_email_lock_key(email)) is not None
    return LockoutState(
        locked=locked,
        reason='account_locked' if locked else '',
        retry_after_seconds=int(ttl) if (locked and ttl) else 0,
    )


def check_ip_lockout(ip: str) -> LockoutState:
    """Same as account check, by IP."""
    if not ip:
        return LockoutState(locked=False)
    ttl = cache.ttl(_ip_lock_key(ip)) if hasattr(cache, 'ttl') else None
    locked = cache.get(_ip_lock_key(ip)) is not None
    return LockoutState(
        locked=locked,
        reason='ip_locked' if locked else '',
        retry_after_seconds=int(ttl) if (locked and ttl) else 0,
    )


def record_failed_login(*, email: str, ip: str, user_agent: str = '',
                        reason: str = 'bad_credentials') -> dict:
    """Atomic counter bump + lockout-threshold check + audit row.

    Returns a dict with diagnostic info. The view never branches on
    this — it always returns the same generic error to the client.
    The dict is for logging and the notification dispatcher.

    Guarantees:
      • cache.incr is atomic; the threshold-crossing decision is
        race-free under any number of concurrent failures.
      • The audit row is written EVEN IF the cache write fails (the
        cache may be down — the row is still the durable record).
    """
    from .login_attempt_models import LoginAttempt

    email_n = _norm_email(email)
    triggered = False
    new_count = 0
    new_ip_count = 0
    lockout_duration_s = 0

    # Per-email counter — only meaningful when we have an email.
    if email_n:
        try:
            new_count = _incr_with_window(_email_count_key(email_n),
                                           ATTEMPT_WINDOW_S)
        except Exception:
            log.exception('lockout: email counter incr failed')
        # Threshold? Set the lock key. Idempotent — concurrent writes
        # of the same value race harmlessly.
        duration = _duration_for_count(new_count)
        if duration is not None:
            try:
                cache.set(_email_lock_key(email_n), True, timeout=duration)
                lockout_duration_s = duration
                triggered = True
            except Exception:
                log.exception('lockout: email lock set failed')

    # Per-IP counter — independent. Stuffing attacks don't need a real
    # email to spike the IP counter (every miss counts).
    if ip:
        try:
            new_ip_count = _incr_with_window(_ip_count_key(ip),
                                              ATTEMPT_WINDOW_S)
        except Exception:
            log.exception('lockout: ip counter incr failed')
        if new_ip_count >= IP_LOCKOUT_THRESHOLD:
            try:
                cache.set(_ip_lock_key(ip), True,
                          timeout=IP_LOCKOUT_DURATION_S)
            except Exception:
                log.exception('lockout: ip lock set failed')

    # Audit row — always written. Failures here are logged but not raised
    # so an auth failure due to login-attempts table issues never blocks
    # the auth response.
    try:
        LoginAttempt.objects.create(
            email=email_n[:255], ip=ip or None,
            user_agent=(user_agent or '')[:400],
            succeeded=False,
            failure_reason=reason[:24],
            triggered_lockout=triggered,
        )
    except Exception:
        log.exception('lockout: audit row write failed')

    return {
        'new_email_count': new_count,
        'new_ip_count': new_ip_count,
        'triggered_account_lockout': triggered,
        'lockout_duration_s': lockout_duration_s,
    }


def record_successful_login(*, email: str, ip: str, user_agent: str = '',
                            user_id=None) -> None:
    """Clear counters + write audit row.

    Called from inside the login serializer AFTER all auth checks
    have passed (including 2FA). Idempotent — clearing an
    already-clear counter is a no-op.
    """
    from .login_attempt_models import LoginAttempt
    email_n = _norm_email(email)
    try:
        cache.delete(_email_count_key(email_n))
        cache.delete(_email_lock_key(email_n))
    except Exception:
        log.exception('lockout: clear email keys failed')
    try:
        LoginAttempt.objects.create(
            email=email_n[:255], ip=ip or None,
            user_agent=(user_agent or '')[:400],
            succeeded=True,
        )
    except Exception:
        log.exception('lockout: success audit write failed')


def clear_lockout(email: str, *, reason: str = 'manual') -> bool:
    """Explicit unlock — called from:
      • password-reset success (legitimate user proved ownership)
      • admin "unlock account" action
      • email-change confirmation (user proved email control)

    Returns True if the user WAS locked (for telemetry / response).
    """
    email_n = _norm_email(email)
    was_locked = cache.get(_email_lock_key(email_n)) is not None
    try:
        cache.delete(_email_count_key(email_n))
        cache.delete(_email_lock_key(email_n))
    except Exception:
        log.exception('lockout: clear_lockout cache delete failed')
    if was_locked:
        log.info('lockout: cleared lock on %s (reason=%s)', email_n, reason)
    return was_locked


def should_send_lockout_notification(email: str) -> bool:
    """Notification dedupe gate. Returns True if we haven't notified
    this email in the last NOTIFICATION_DEDUPE_S seconds, AND atomically
    records that we're about to notify.

    Race-safe via cache.add() — only one worker sees True under burst."""
    return cache.add(_notif_dedupe_key(email), True,
                     timeout=NOTIFICATION_DEDUPE_S)


# ── Timing-equalisation helper ─────────────────────────────────────────────

# Pre-computed at import time so the first call doesn't pay the bcrypt
# CPU cost. The hash is salted, so check_password() against this will
# always fail in roughly the same time it takes a real check_password()
# against a stored user hash. This kills the user-existence timing leak.
_DUMMY_HASH = make_password('this-password-cannot-match-any-real-user-' +
                            '__dummy_for_timing_equalisation__')


def equalize_timing(password: str) -> None:
    """For the 'email not found' path: burn the same CPU as a real
    check_password() so the response time is indistinguishable.

    Without this, attackers can detect non-existent emails by timing:
    the no-user path skips the bcrypt round (microseconds) while the
    real path takes ~100ms. Two orders of magnitude is a strong
    enumeration oracle.
    """
    try:
        check_password(password or '', _DUMMY_HASH)
    except Exception:
        # Defensive: an exception in the hasher must not change timing
        # observably, so swallow and continue.
        pass
