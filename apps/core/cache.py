"""
Safe cache wrapper — never crashes if Redis is down.
Use this instead of raw cache.get/set.
"""
import logging
from django.core.cache import cache as _cache

logger = logging.getLogger('micha')


class SafeCache:
    """
    Wraps Django cache with graceful degradation.
    If Redis is down, operations fail silently and return None/False.
    The app continues to work, just without caching.
    """

    def get(self, key, default=None):
        try:
            return _cache.get(key, default)
        except Exception as e:
            logger.warning(f'Cache GET failed for {key}: {e}')
            return default

    def set(self, key, value, timeout=300):
        try:
            return _cache.set(key, value, timeout=timeout)
        except Exception as e:
            logger.warning(f'Cache SET failed for {key}: {e}')
            return False

    def delete(self, key):
        try:
            return _cache.delete(key)
        except Exception as e:
            logger.warning(f'Cache DELETE failed for {key}: {e}')
            return False

    def get_or_set(self, key, default, timeout=300):
        try:
            return _cache.get_or_set(key, default, timeout=timeout)
        except Exception as e:
            logger.warning(f'Cache GET_OR_SET failed for {key}: {e}')
            return default() if callable(default) else default


safe_cache = SafeCache()
