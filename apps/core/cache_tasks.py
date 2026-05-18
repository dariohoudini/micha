"""
apps/core/cache_tasks.py

Celery tasks for cache_kit's async SWR refresh path. Lives in core
because cache_kit itself can't import celery without making the kit
hard to use from synchronous contexts (e.g. management commands).

The task simply re-runs the loader for a registered key. Loaders are
registered at module import time via ``register_loader`` so the task
can look them up by key prefix.
"""
from __future__ import annotations

import logging
from celery import shared_task

from apps.core.task_locks import singleton_task


log = logging.getLogger(__name__)

# Registry of {key_prefix: loader_callable}. Modules that want async
# refresh register their loader at import time:
#
#   from apps.core.cache_tasks import register_loader
#   register_loader('product_detail:', _build_product_detail_payload)
#
# At refresh time we match the cache key against registered prefixes.
_LOADERS: dict[str, callable] = {}


def register_loader(prefix: str, loader):
    """Register a loader for keys matching the given prefix.

    The loader is called with the FULL cache key so it can extract any
    dynamic suffix (e.g. product slug, user id). It must produce the
    same value as the in-line loader for the same key.
    """
    _LOADERS[prefix] = loader


@shared_task(name='cache.refresh_cache_entry', bind=True, max_retries=1)
@singleton_task('beat:cache.refresh_cache_entry')
def refresh_cache_entry(self, key: str):
    """Rebuild a cache entry out-of-band.

    Looks up the registered loader by key prefix, executes it, stores
    the result. Used by cached_call(async_refresh=True) so user-facing
    requests never pay the SWR refresh cost.
    """
    from apps.core.cache_kit import cached_call

    for prefix, loader in _LOADERS.items():
        if key.startswith(prefix):
            # Force-rebuild via cached_call so we get all the same
            # single-flight + envelope-store semantics.
            try:
                cached_call(
                    key, lambda: loader(key),
                    # The original ttl/swr_ttl is encoded in the
                    # registration; for simplicity we use long-lived
                    # defaults here. Refresh always wins.
                    ttl=300, swr_ttl=600, force=True,
                )
            except Exception as e:
                log.warning('refresh_cache_entry failed for %s: %s', key, e)
            return {'refreshed': key, 'prefix': prefix}
    log.info('refresh_cache_entry: no loader registered for key=%s', key)
    return {'refreshed': None, 'reason': 'no_loader'}
