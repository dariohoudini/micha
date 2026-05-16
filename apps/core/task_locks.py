"""
apps/core/task_locks.py

@singleton_task — wraps a Celery task body so that only one worker can
execute it at a time, cluster-wide, across processes and hosts. Uses the
advisory_lock primitive — Postgres in prod, file lock in dev.

When the lock is held by another worker, this worker silently no-ops
(returning a sentinel). That's the right default for beat-fired tasks
which fire repeatedly anyway: "another worker is on it" is normal, not
an error.

Usage:
    @shared_task(name='foo.bar')
    @singleton_task('foo.bar')
    def bar():
        do_work()

Or inline:
    @shared_task(name='foo.bar')
    def bar():
        with advisory_lock('foo.bar') as got:
            if not got:
                return 'skipped: held'
            do_work()
"""
from __future__ import annotations
import functools
import logging

from .locks import advisory_lock

log = logging.getLogger(__name__)


def singleton_task(lock_key: str = ''):
    """Decorator factory. ``lock_key`` defaults to the wrapped function's name.

    The protected section runs only when the lock is free. If the lock is
    held by another worker, we return a sentinel dict so callers/operators
    can still see "I tried, someone else owns it" in task results.
    """
    def decorator(fn):
        key = lock_key or f'task:{fn.__module__}.{fn.__name__}'

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with advisory_lock(key, timeout=0) as got:
                if not got:
                    log.info('singleton_task %s: held elsewhere, skipping', key)
                    return {'skipped': True, 'reason': 'lock_held', 'key': key}
                return fn(*args, **kwargs)
        return wrapper
    return decorator
