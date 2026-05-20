"""
middleware/db_timeout.py
─────────────────────────

Per-request + ad-hoc DB statement-timeout control.

Why this exists
────────────────
config/settings.py sets a connection-level
``-c statement_timeout=30000`` (30 seconds) which is the right
absolute ceiling, but too generous for hot read paths. Three real
production-grade gaps in "one timeout for everything":

  1. Autocomplete / search / product list — these should fail in
     < 2 s. A pathological input that doesn't blow out the search
     hardening (commit 2f47967) but DOES match millions of rows
     would still hold a connection for 30 seconds before the
     connection-level guard fires. At 10k req/s that's the entire
     pool wedged in 30 s.

  2. Admin reports / exports — sometimes legitimately need 5+
     minutes. Today they're capped by the global 30s and FAIL
     during routine ops work. Operators work around it by skipping
     the gateway and running raw SQL — defeating the audit trail.

  3. No way to bound a SPECIFIC critical-section query (e.g.
     a payout disbursement query that must NEVER take more than
     5 seconds). Today it inherits whatever the connection has,
     which is "whatever the last request set".

This module provides:

  set_statement_timeout(ms)
      Set the timeout on the current connection. Postgres only;
      SQLite + other backends are no-ops.

  statement_timeout(ms) [context manager]
      Save the current timeout, set new, restore on exit. Use this
      to BOUND a critical section without leaving the new value as
      a side effect on the pooled connection.

  PerPathStatementTimeoutMiddleware
      Reads settings.DB_STATEMENT_TIMEOUT_BY_PATH (prefix → ms) and
      applies the matching timeout for the duration of the request.
      Restores the default on response.

Why pooled-connection safety matters
─────────────────────────────────────
Django keeps connections alive across requests (CONN_MAX_AGE=60). If
request A does ``SET statement_timeout = 2000`` and crashes before
restoring, request B reuses the same connection and inherits the
2 s cap — silently. The middleware ALWAYS restores in the finally
block; the context manager does the same. The defensive value is the
connection-options default (30 s) — set at startup via the DSN, so
even if a Python exception escapes both restorers, a fresh connection
recreates with the default.

Settings
─────────
  DB_STATEMENT_TIMEOUT_DEFAULT_MS = 30000   (matches the DSN options)
  DB_STATEMENT_TIMEOUT_BY_PATH = {
      '/api/v1/search/':        2000,
      '/api/v1/autocomplete':   1500,
      '/api/v1/products/':      5000,
      '/api/v1/admin/reports/': 300000,  # 5 minutes
  }
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Optional

from django.conf import settings
from django.db import connection


log = logging.getLogger(__name__)


def _is_postgres() -> bool:
    """True if the default connection is Postgres. SQLite/SQLite-test
    paths cleanly no-op so the smoke test can validate plumbing
    without a real Postgres."""
    try:
        return connection.vendor == 'postgresql'
    except Exception:
        return False


def _default_ms() -> int:
    return int(getattr(settings, 'DB_STATEMENT_TIMEOUT_DEFAULT_MS', 30_000))


def _by_path() -> dict:
    return dict(getattr(settings, 'DB_STATEMENT_TIMEOUT_BY_PATH', {}) or {})


def set_statement_timeout(ms: int) -> None:
    """Set the Postgres statement_timeout for the current connection.

    On non-Postgres backends this is a no-op (safe for SQLite-backed
    smoke tests + dev environments).

    Args:
      ms: timeout in milliseconds. 0 means "no timeout" — avoid.
    """
    if not _is_postgres():
        return
    try:
        # SET (without LOCAL) persists for the session. The middleware
        # always restores in finally; the context manager does too.
        with connection.cursor() as cur:
            cur.execute('SET statement_timeout = %s', [int(ms)])
    except Exception:
        # NEVER raise from a timeout-setter — it would block the
        # request entirely on a transient DB hiccup.
        log.warning('db_timeout.set: failed to set statement_timeout to %s',
                    ms, exc_info=True)


def get_statement_timeout() -> Optional[int]:
    """Return the current statement_timeout in milliseconds, or None
    on non-Postgres / on read failure."""
    if not _is_postgres():
        return None
    try:
        with connection.cursor() as cur:
            cur.execute('SHOW statement_timeout')
            row = cur.fetchone()
        if not row:
            return None
        # SHOW returns a human string: '2s', '500ms', '0'.
        return _parse_pg_timeout(row[0])
    except Exception:
        return None


def _parse_pg_timeout(s: str) -> int:
    """Parse Postgres timeout strings ('2s', '500ms', '0') to ms."""
    if not s:
        return 0
    s = s.strip().lower()
    if s == '0':
        return 0
    if s.endswith('ms'):
        return int(s[:-2])
    if s.endswith('s'):
        return int(float(s[:-1]) * 1000)
    if s.endswith('min'):
        return int(float(s[:-3]) * 60 * 1000)
    try:
        return int(s)  # raw number of ms
    except ValueError:
        return 0


@contextmanager
def statement_timeout(ms: int):
    """Context manager: bound a code block by a Postgres statement_timeout.

    Saves the current timeout, sets the new one for the duration of
    the block, restores ON EXIT (success OR exception). Use to:

      • Tighten a critical-section query that MUST fail fast
        (e.g. autocomplete on a hot endpoint)
      • Loosen a legitimately-long admin operation back from the
        per-path default

    Usage:
        with statement_timeout(1500):
            results = ProductSearchService.search(query, limit=5)

    On non-Postgres backends, the context manager runs but doesn't
    actually adjust anything — safe to wrap code that will be tested
    against SQLite.
    """
    if not _is_postgres():
        yield
        return

    previous = get_statement_timeout()
    set_statement_timeout(ms)
    try:
        yield
    finally:
        if previous is not None:
            set_statement_timeout(previous)
        else:
            # Couldn't read the previous value — restore the default
            # so we never leave a tight cap on the pooled connection.
            set_statement_timeout(_default_ms())


# ─── Middleware ──────────────────────────────────────────────────────

class PerPathStatementTimeoutMiddleware:
    """Apply a per-path statement_timeout for the duration of the
    request. Restores the default on response.

    Lookup is by longest-matching path PREFIX in
    ``settings.DB_STATEMENT_TIMEOUT_BY_PATH``. Unmatched paths use
    ``DB_STATEMENT_TIMEOUT_DEFAULT_MS``.

    Connection-pool safety
    ───────────────────────
    Django keeps connections alive (CONN_MAX_AGE). Without a restore,
    request A's tight 2 s cap would persist for the next request that
    reuses the connection. The ``finally`` here ALWAYS runs — even on
    a view exception. The DSN-level default (set in settings.DATABASES
    OPTIONS) is the floor if both the finally AND the DB cursor itself
    fail.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not _is_postgres():
            return self.get_response(request)

        path = request.path or ''
        timeout_ms = self._lookup(path)

        if timeout_ms is None:
            return self.get_response(request)

        set_statement_timeout(timeout_ms)
        try:
            return self.get_response(request)
        finally:
            # Restore default. We don't try to read the previous value
            # here — that's a roundtrip per request. The middleware
            # owns the per-request value entirely.
            try:
                set_statement_timeout(_default_ms())
            except Exception:
                log.warning('db_timeout: restore failed', exc_info=True)

    def _lookup(self, path: str) -> Optional[int]:
        """Longest-prefix match against DB_STATEMENT_TIMEOUT_BY_PATH."""
        by_path = _by_path()
        if not by_path:
            return None
        best: tuple[int, Optional[int]] = (-1, None)  # (prefix_len, ms)
        for prefix, ms in by_path.items():
            if path.startswith(prefix) and len(prefix) > best[0]:
                best = (len(prefix), int(ms))
        return best[1]
