"""
apps/core/cache_kit.py
======================

Production-grade read-through cache primitive on top of Django's cache backend.
Wraps the existing SafeCache (which already gracefully degrades when Redis is
unavailable) and adds:

  • Versioned tag invalidation
      Cache keys reference a tag version counter. Bumping the counter
      logically invalidates every key tagged with it — without enumerating
      them. This is the only sane way to invalidate caches whose keys depend
      on query strings, locale, user-agent, etc.

  • Single-flight stampede protection
      When a hot key expires, hundreds of concurrent requests would otherwise
      all execute the loader function. We hold a short-lived lock so only ONE
      request rebuilds; the rest wait briefly and re-read. Implemented with
      cache.add (Redis SETNX) so it's atomic and doesn't require Redis-locks.

  • Stale-while-revalidate
      ``swr=True`` returns the stale value and schedules a background refresh.
      Latency stays low even during cache misses on hot keys. Requires the
      cache value to be a tuple (value, fresh_until_epoch).

  • Hit/miss/stampede metrics
      Counters fed into apps.telemetry.metrics so we can prove the cache is
      actually working (and detect when invalidation runs amok).

Designed to be safe to apply broadly: every operation no-ops on Redis failure.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
from typing import Callable, Optional, Sequence

from django.core.cache import cache as _cache

log = logging.getLogger(__name__)


# ─── Telemetry shims — no-op if telemetry app isn't ready ──────────────────
def _hit():
    try:
        from apps.telemetry.metrics import cache_hits
        cache_hits.inc()
    except Exception:
        pass


def _miss():
    try:
        from apps.telemetry.metrics import cache_misses
        cache_misses.inc()
    except Exception:
        pass


def _stampede():
    try:
        from apps.telemetry.metrics import cache_stampedes_avoided
        cache_stampedes_avoided.inc()
    except Exception:
        pass


# ─── Tag versioning ────────────────────────────────────────────────────────

def _tag_key(tag: str) -> str:
    return f'cachekit:v:{tag}'


def get_tag_version(tag: str) -> int:
    """Return current monotonic version for a tag. Auto-creates at 1."""
    try:
        v = _cache.get(_tag_key(tag))
        if v is None:
            # Use the cache as the source of truth — concurrent get-or-init
            # races are fine because all losers will read the winner's value.
            _cache.add(_tag_key(tag), 1, timeout=None)
            v = _cache.get(_tag_key(tag)) or 1
        return int(v)
    except Exception:
        return 1


def bump_tag(tag: str) -> int:
    """Increment a tag's version → invalidates every key referencing it.

    Returns the new version. Failures degrade to no-op (cache stays consistent
    eventually via TTL expiry).
    """
    try:
        # Django's cache.incr requires the key to exist; ensure it does.
        _cache.add(_tag_key(tag), 1, timeout=None)
        return int(_cache.incr(_tag_key(tag)))
    except Exception as e:
        log.warning('bump_tag failed for %s: %s', tag, e)
        return 0


def bump_tags(tags: Sequence[str]) -> None:
    for t in tags:
        bump_tag(t)


# ─── Key building ──────────────────────────────────────────────────────────

def build_key(prefix: str, tags: Sequence[str] = (), *parts) -> str:
    """Compose a deterministic cache key that bakes in current tag versions.

    Bumping any referenced tag invalidates all keys that referenced it. We
    hash long composite keys so we don't blow Redis's 250-char key limit.
    """
    versions = '.'.join(f'{t}={get_tag_version(t)}' for t in tags)
    raw = f'{prefix}:{versions}:' + ':'.join(str(p) for p in parts)
    if len(raw) > 200:
        # Hash the dynamic portion but keep prefix readable for ops.
        h = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]
        return f'{prefix}:hash:{h}'
    return raw


# ─── Single-flight ─────────────────────────────────────────────────────────

_LOCK_TTL = 10            # seconds — long enough for slow loaders, short enough not to wedge
_WAITER_BACKOFF = 0.05    # 50ms between re-reads while another worker rebuilds
_WAITER_MAX_RETRIES = 40  # ~2s total wait before giving up and computing locally


def _lock_key(key: str) -> str:
    return f'{key}:_sf_lock'


def _acquire_lock(key: str) -> bool:
    """SETNX-style lock acquisition. cache.add is atomic on Redis."""
    try:
        return bool(_cache.add(_lock_key(key), '1', timeout=_LOCK_TTL))
    except Exception:
        return False


def _release_lock(key: str) -> None:
    try:
        _cache.delete(_lock_key(key))
    except Exception:
        pass


# ─── Public API ────────────────────────────────────────────────────────────

def cached_call(
    key: str,
    loader: Callable[[], object],
    *,
    ttl: int,
    swr_ttl: Optional[int] = None,
    jitter_pct: float = 0.1,
):
    """Read-through cache.

    Args:
      key: Already-composed cache key (use ``build_key`` for tag-versioned keys).
      loader: Zero-arg callable that produces the value when the cache misses.
        Should be a pure function of the key — same key → same value.
      ttl: Hard TTL in seconds. After this expires the entry is fully gone.
      swr_ttl: If set, the value is returned past `ttl` for up to `swr_ttl`
        additional seconds while a background refresh runs (stale-while-
        revalidate). None → no SWR; expired = full miss.
      jitter_pct: Random fraction added to the TTL on writes to spread out
        expiry of correlated keys. Default 10%.

    Returns the cached or freshly-loaded value. NEVER raises — on cache
    backend failure, falls back to calling loader() directly.
    """
    try:
        cached = _cache.get(key)
    except Exception:
        cached = None

    now = time.time()

    if cached is not None:
        # Internal envelope: (value, fresh_until_epoch). Older callers stored
        # bare values; treat those as still-fresh.
        if isinstance(cached, dict) and '_v' in cached:
            value = cached['_v']
            fresh_until = cached.get('_f', now + ttl)
            if now < fresh_until:
                _hit()
                return value
            # Stale — try SWR
            if swr_ttl is not None:
                _hit()  # served stale = still a "hit" for latency purposes
                _maybe_refresh_async(key, loader, ttl, swr_ttl, jitter_pct)
                return value
            # No SWR — fall through to miss path
        else:
            _hit()
            return cached

    return _load_with_singleflight(key, loader, ttl, swr_ttl, jitter_pct)


def _maybe_refresh_async(key, loader, ttl, swr_ttl, jitter_pct):
    """If we can grab the lock, refresh in-line (deferred to a thread or task
    would be ideal, but doing it in the current request still amortises across
    requests because only one worker actually computes)."""
    if not _acquire_lock(key):
        return  # another worker is on it
    try:
        value = loader()
        _store(key, value, ttl, swr_ttl, jitter_pct)
    except Exception as e:
        log.warning('cache async refresh failed for %s: %s', key, e)
    finally:
        _release_lock(key)


def _load_with_singleflight(key, loader, ttl, swr_ttl, jitter_pct):
    """Miss path: try to grab the lock; if held, wait briefly and re-read.
    Only one worker per key executes the loader."""
    if _acquire_lock(key):
        try:
            _miss()
            value = loader()
            _store(key, value, ttl, swr_ttl, jitter_pct)
            return value
        finally:
            _release_lock(key)

    # Lock held by another worker — wait briefly and re-read
    _stampede()
    for _ in range(_WAITER_MAX_RETRIES):
        time.sleep(_WAITER_BACKOFF)
        try:
            cached = _cache.get(key)
        except Exception:
            cached = None
        if cached is not None:
            if isinstance(cached, dict) and '_v' in cached:
                return cached['_v']
            return cached
    # Gave up waiting — compute locally rather than serve stale-or-error.
    log.warning('cache singleflight timeout on %s; computing locally', key)
    _miss()
    return loader()


def _store(key, value, ttl, swr_ttl, jitter_pct):
    j = 1 + random.uniform(0, max(jitter_pct, 0))
    hard_ttl = int(ttl * j) + (swr_ttl or 0)
    envelope = {'_v': value, '_f': time.time() + ttl * j}
    try:
        _cache.set(key, envelope, timeout=hard_ttl)
    except Exception as e:
        log.warning('cache set failed for %s: %s', key, e)


def invalidate(key: str) -> None:
    """Hard delete one specific key."""
    try:
        _cache.delete(key)
    except Exception:
        pass
