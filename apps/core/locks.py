"""
apps/core/locks.py

Cross-process advisory locks. Solves the classic "two Celery workers fire
the same scheduled task at the same minute" problem, and the matching
in-request bug where two admin clicks resolve the same dispute simultaneously.

Backends:
  • Postgres: pg_advisory_lock / pg_try_advisory_lock (session-scoped, must
    explicitly release). Locks are scoped to a 64-bit integer key; we hash
    the human-readable string to derive the key.
  • SQLite (dev): file-based fcntl lock as a fallback so dev tests still
    work without Postgres.

Usage:
    with advisory_lock('beat.enforce_return_deadlines', timeout=5) as got:
        if not got:
            return  # someone else is running it
        do_work()

Properties:
  • Acquisition NEVER raises — lock backend failure falls through to
    "didn't get it", which is the safer default.
  • Release is best-effort. A crashed Python process drops its Postgres
    session, which drops the lock — no permanent wedging.
  • The same key in two different DB connections cannot both acquire.
"""
from __future__ import annotations
import contextlib
import hashlib
import logging
import os
import struct
import time

from django.db import connections, OperationalError

log = logging.getLogger(__name__)


def _key_to_int(key: str) -> int:
    """SHA-256 the key, take the first 8 bytes, interpret as signed int64
    (Postgres advisory locks take a bigint)."""
    digest = hashlib.sha256(key.encode('utf-8')).digest()[:8]
    return struct.unpack('>q', digest)[0]


def _is_postgres() -> bool:
    return connections['default'].vendor == 'postgresql'


@contextlib.contextmanager
def advisory_lock(key: str, timeout: float = 0.0):
    """Context manager that yields True iff we acquired the lock.

    Args:
      key: human-readable lock name. Same string from two processes locks
           the same row.
      timeout: seconds to wait for the lock. 0 = pure try (return False
               immediately if held). >0 = poll with backoff up to ``timeout``.

    The caller MUST branch on the yielded boolean — yielding False is the
    runtime's way of saying "someone else owns this; skip the work".

    Yields:
      bool — True if we acquired and own the lock; False if it was held
      and we should not run the protected section.
    """
    got = False
    release = lambda: None
    try:
        if _is_postgres():
            got, release = _pg_acquire(key, timeout)
        else:
            got, release = _file_acquire(key, timeout)
    except Exception as e:
        # Lock backend failure → fall through as "didn't get it" so the
        # caller skips work rather than running unguarded.
        log.warning('advisory_lock %s failed to acquire: %s', key, e)
        got = False

    try:
        yield got
    finally:
        if got:
            try:
                release()
            except Exception as e:
                log.warning('advisory_lock %s release failed: %s', key, e)


# ─── Postgres backend ──────────────────────────────────────────────────────

def _pg_acquire(key: str, timeout: float):
    k = _key_to_int(key)
    conn = connections['default']

    deadline = time.monotonic() + timeout
    backoff = 0.05  # 50ms initial

    while True:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(%s)', [k])
            got = bool(cur.fetchone()[0])
        if got:
            def _release(_k=k, _conn=conn):
                with _conn.cursor() as c:
                    c.execute('SELECT pg_advisory_unlock(%s)', [_k])
            return True, _release
        if time.monotonic() >= deadline:
            return False, lambda: None
        time.sleep(backoff)
        backoff = min(backoff * 2, 0.5)


# ─── SQLite / dev backend ──────────────────────────────────────────────────

def _file_acquire(key: str, timeout: float):
    """fcntl lock on a file per key. Cross-process but local-fs only —
    sufficient for dev and CI; production runs Postgres."""
    import fcntl
    import tempfile

    safe = hashlib.sha256(key.encode()).hexdigest()[:16]
    path = os.path.join(tempfile.gettempdir(), f'micha-lock-{safe}.lock')
    f = open(path, 'w')

    deadline = time.monotonic() + timeout
    backoff = 0.05
    while True:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def _release(_f=f):
                try:
                    fcntl.flock(_f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    _f.close()
                except Exception:
                    pass
            return True, _release
        except BlockingIOError:
            if time.monotonic() >= deadline:
                try:
                    f.close()
                except Exception:
                    pass
                return False, lambda: None
            time.sleep(backoff)
            backoff = min(backoff * 2, 0.5)
