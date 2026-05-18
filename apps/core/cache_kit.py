"""
apps/core/cache_kit.py
======================

Production-grade read-through cache primitive on top of Django's cache
backend. Built for an e-commerce app under viral / Black-Friday load
where popular cache keys expire under thousands of concurrent requests.

Features
─────────
  • Versioned tag invalidation
      Cache keys reference a tag version counter. Bumping the counter
      logically invalidates every key tagged with it — without
      enumerating them. The only sane way to invalidate caches whose
      keys depend on query strings, locale, user-agent, etc.

  • Single-flight stampede protection (with token-fenced locks)
      When a hot key expires, hundreds of concurrent requests would
      otherwise all execute the loader. We hold a short-lived lock so
      only ONE request rebuilds; the rest wait briefly and re-read.
      The lock stores a UNIQUE TOKEN — release only deletes the lock
      if the token still matches, preventing the classic stale-lock-
      release bug:

        Without token fencing:
          W1 acquires lock (TTL=10s); loader hangs for 12s.
          Lock auto-expires.
          W2 acquires now-free lock.
          W1's loader finishes, calls delete(lock) → DELETES W2's LOCK.
          W3 arrives, sees no lock, acquires it.
          Now W2 + W3 BOTH load. Stampede defeated.

        With token fencing:
          W1 releases — but its token doesn't match W2's, so the
          delete is skipped. W2's lock survives until its own TTL.

  • Stale-while-revalidate (in-line OR via Celery)
      ``swr_ttl`` returns the stale value past TTL while a background
      refresh runs. Two refresh modes:
        - default: in-line (deferred lock acquisition by ONE worker)
        - async_refresh=True: enqueue a Celery task so the user-facing
          request returns immediately and never pays the loader cost.

  • Hit / miss / stampede / negative-cache metrics fed into Prometheus.

  • Negative caching (``negative_ttl=N``)
      Loaders that return None / empty are cached for ``negative_ttl``
      seconds (shorter than the positive TTL) to absorb hammering on
      legitimately-empty results (search for a nonexistent product,
      missing slug, etc.) WITHOUT permanently masking real data.

  • Force-refresh hook (``cached_call(..., force=True)``)
      Operator escape hatch: rebuild this key now regardless of
      cache state. Honours single-flight so concurrent force-refreshes
      coalesce.

Designed to be safe to apply broadly: every operation no-ops on Redis
failure — the worst case is we fall back to calling the loader.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
import uuid
from typing import Any, Callable, Optional, Sequence

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
            _cache.add(_tag_key(tag), 1, timeout=None)
            v = _cache.get(_tag_key(tag)) or 1
        return int(v)
    except Exception:
        return 1


def bump_tag(tag: str) -> int:
    """Increment a tag's version → invalidates every key referencing it.

    Returns the new version. Failures degrade to no-op (cache stays
    consistent eventually via TTL expiry).
    """
    try:
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
    """Compose a deterministic cache key that bakes in current tag
    versions. We hash long composite keys so we don't blow Redis's
    250-char key limit.
    """
    versions = '.'.join(f'{t}={get_tag_version(t)}' for t in tags)
    raw = f'{prefix}:{versions}:' + ':'.join(str(p) for p in parts)
    if len(raw) > 200:
        h = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]
        return f'{prefix}:hash:{h}'
    return raw


# ─── Single-flight with token-fenced locks ─────────────────────────────────

_DEFAULT_LOCK_TTL = 10            # seconds — covers most loaders
_WAITER_BACKOFF = 0.05            # 50ms between re-reads while another worker rebuilds
_WAITER_MAX_RETRIES_DEFAULT = 60  # ~3s total wait before giving up


def _lock_key(key: str) -> str:
    return f'{key}:_sf_lock'


def _acquire_lock(key: str, *, ttl: int) -> Optional[str]:
    """Atomic SETNX with a UNIQUE TOKEN as the stored value.

    Returns the token on success, None on failure (lock held by
    someone else). The token is required to release the lock —
    prevents the stale-lock-release race described in the module
    docstring.
    """
    token = uuid.uuid4().hex
    try:
        if _cache.add(_lock_key(key), token, timeout=ttl):
            return token
    except Exception:
        pass
    return None


def _release_lock(key: str, token: str) -> None:
    """Release ONLY IF the lock still contains our token.

    Django's cache backend doesn't support atomic compare-and-delete
    across the board, so we do a get-then-delete with a token check.
    The race window is small (microseconds) and the worst case if
    we lose the race is: we delete a freshly-acquired lock from
    another worker — but that worker will detect the missing lock on
    its own re-read and either retry or compute locally. The stampede
    blast radius is bounded.

    For Redis specifically, the proper atomic variant would be a Lua
    script; that's a future hardening if we see lock thrash in metrics.
    """
    try:
        current = _cache.get(_lock_key(key))
        if current == token:
            _cache.delete(_lock_key(key))
    except Exception:
        pass


# ─── Public API ────────────────────────────────────────────────────────────

# Sentinel returned by loaders that want to opt OUT of negative caching
# for THIS specific call (e.g. "this empty result is transient, don't
# cache it as empty").
NO_CACHE = object()


def cached_call(
    key: str,
    loader: Callable[[], Any],
    *,
    ttl: int,
    swr_ttl: Optional[int] = None,
    jitter_pct: float = 0.1,
    negative_ttl: Optional[int] = None,
    lock_ttl: int = _DEFAULT_LOCK_TTL,
    waiter_max_retries: int = _WAITER_MAX_RETRIES_DEFAULT,
    force: bool = False,
    async_refresh: bool = False,
):
    """Read-through cache with stampede protection.

    Args:
      key: Already-composed cache key (use ``build_key`` for tag-versioned).
      loader: Zero-arg callable that produces the value when the cache
        misses. Should be a pure function of the key. May return
        ``NO_CACHE`` to opt out of caching this particular result.
      ttl: Hard TTL in seconds for positive (non-empty) results.
      swr_ttl: If set, the value is returned past `ttl` for up to
        `swr_ttl` additional seconds while a background refresh runs.
      jitter_pct: Random fraction added to the TTL on writes (default 10%)
        to spread out expiry of correlated keys. Prevents synchronised
        re-fetches after a deploy that warms many entries at once.
      negative_ttl: TTL for None / empty results. If unset, falsy
        values fall through to ``ttl``. Setting this to a short value
        absorbs hammering on legitimately-empty results.
      lock_ttl: How long the single-flight lock is held. Must be at
        least as long as the slowest expected loader. Default 10s.
      waiter_max_retries: How many 50ms ticks a waiter polls before
        falling back to local compute (after which it gives up and
        loads itself). Default 60 = 3s. For loaders >3s, raise this.
      force: If True, bypass the cache read and rebuild now. Still
        honours single-flight (concurrent force=True calls coalesce).
      async_refresh: If True, SWR refresh enqueues a Celery task
        instead of refreshing in the request thread. Default False.

    Returns the cached or freshly-loaded value. NEVER raises — on
    cache backend failure, falls back to calling loader() directly.
    """
    now = time.time()

    if not force:
        try:
            cached = _cache.get(key)
        except Exception:
            cached = None

        if cached is not None:
            value, fresh_until = _unpack(cached, now, ttl)
            if now < fresh_until:
                _hit()
                return value
            # Stale — SWR path?
            if swr_ttl is not None:
                _hit()
                _maybe_refresh(
                    key, loader, ttl, swr_ttl, jitter_pct,
                    negative_ttl, lock_ttl, async_refresh,
                )
                return value
            # No SWR — fall through to miss path

    return _load_with_singleflight(
        key, loader, ttl, swr_ttl, jitter_pct,
        negative_ttl, lock_ttl, waiter_max_retries,
    )


def _unpack(cached, now, ttl):
    """Internal envelope: {'_v': value, '_f': fresh_until_epoch}.

    Older callers stored bare values; treat those as still-fresh
    (use the configured ttl as the fresh-until reference)."""
    if isinstance(cached, dict) and '_v' in cached:
        return cached['_v'], cached.get('_f', now + ttl)
    return cached, now + ttl


def _maybe_refresh(key, loader, ttl, swr_ttl, jitter_pct,
                   negative_ttl, lock_ttl, async_refresh):
    """SWR refresh path. Only ONE worker per key actually rebuilds."""
    if async_refresh:
        # Enqueue a celery task — request returns immediately.
        try:
            from .cache_tasks import refresh_cache_entry
            refresh_cache_entry.delay(key)
            return
        except Exception:
            log.warning('cache async refresh enqueue failed; falling back '
                        'to in-line refresh')
            # Fall through to in-line — better than no refresh.

    token = _acquire_lock(key, ttl=lock_ttl)
    if token is None:
        return  # another worker is on it
    try:
        value = loader()
        _store(key, value, ttl, swr_ttl, jitter_pct, negative_ttl)
    except Exception as e:
        log.warning('cache async refresh failed for %s: %s', key, e)
    finally:
        _release_lock(key, token)


def _load_with_singleflight(key, loader, ttl, swr_ttl, jitter_pct,
                            negative_ttl, lock_ttl, waiter_max_retries):
    """Miss path: try to grab the lock; if held, wait briefly and re-read.
    Only one worker per key executes the loader."""
    token = _acquire_lock(key, ttl=lock_ttl)
    if token is not None:
        try:
            _miss()
            value = loader()
            _store(key, value, ttl, swr_ttl, jitter_pct, negative_ttl)
            return value
        finally:
            _release_lock(key, token)

    # Lock held by another worker — wait and re-read.
    _stampede()
    for _ in range(waiter_max_retries):
        time.sleep(_WAITER_BACKOFF)
        try:
            cached = _cache.get(key)
        except Exception:
            cached = None
        if cached is not None:
            if isinstance(cached, dict) and '_v' in cached:
                return cached['_v']
            return cached
    # Gave up waiting — compute locally rather than serve nothing.
    # This is the only path that can produce a duplicate loader call
    # under stampede; configurable via ``waiter_max_retries`` for
    # known-slow loaders.
    log.warning('cache singleflight timeout on %s after %d retries; '
                'computing locally', key, waiter_max_retries)
    _miss()
    return loader()


def _store(key, value, ttl, swr_ttl, jitter_pct, negative_ttl):
    """Write the cache envelope with jittered TTL.

    Empty/None values use the shorter ``negative_ttl`` if provided —
    absorbs hammering on legitimately-empty results without permanently
    masking real data.
    """
    if value is NO_CACHE:
        return
    is_empty = (
        value is None
        or value == ''
        or value == []
        or value == {}
    )
    effective_ttl = ttl
    if is_empty and negative_ttl is not None:
        effective_ttl = negative_ttl
    j = 1 + random.uniform(0, max(jitter_pct, 0))
    hard_ttl = int(effective_ttl * j) + (swr_ttl or 0)
    envelope = {'_v': value, '_f': time.time() + effective_ttl * j}
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


# ─── Convenience decorator for view-level caching ─────────────────────────

def cached_view(*, key_func: Callable, ttl: int, swr_ttl: Optional[int] = None,
                negative_ttl: Optional[int] = None,
                lock_ttl: int = _DEFAULT_LOCK_TTL,
                async_refresh: bool = False):
    """Decorator that wraps an APIView method (or any callable) with
    cached_call(). ``key_func`` receives the same args as the wrapped
    method and returns a cache key.

    Example:
        class FlashSalesView(APIView):
            @cached_view(
                key_func=lambda self, request: 'homepage:flash_sales',
                ttl=300, swr_ttl=600,
            )
            def get(self, request):
                ...
    """
    from functools import wraps

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            return cached_call(
                key, lambda: fn(*args, **kwargs),
                ttl=ttl, swr_ttl=swr_ttl,
                negative_ttl=negative_ttl,
                lock_ttl=lock_ttl,
                async_refresh=async_refresh,
            )
        return wrapper
    return decorator
