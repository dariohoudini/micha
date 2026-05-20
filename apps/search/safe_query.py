"""
apps/search/safe_query.py
──────────────────────────

Input sanitization for the product search path.

Why this exists
────────────────
``ProductSearchService._search_orm`` built a per-token ``OR Q()`` over
``name__icontains`` / ``description__icontains``. Three real production
risks lived in the raw-input handling:

  1. No token-length cap. A single 5000-character token sailed through
     into ``.filter(name__icontains=<5000 chars>)`` — Postgres LIKE
     with a huge pattern on a non-indexed column is a per-row sequential
     scan with quadratic-ish behaviour. One adversarial request pinned
     a worker for seconds.

  2. No wildcard escape. ``icontains`` translates the input to ``LIKE
     %<input>%`` with implicit start/end wildcards but does NOT escape
     ``%`` / ``_`` inside the input. A user typing ``%anything%`` got
     "match anything" semantics. Worse, with adversarial nesting
     (``%%%%%%%`` of length N), the planner produces increasingly
     expensive plans.

  3. No total-query-length cap. A 100 KB query string with valid tokens
     would still be tokenized + filtered + faceted. ``query.strip()``
     materialises the whole thing into Python memory before we even
     consider the token cap.

Also: the autocomplete service pulls suggestions from
``SearchQuery.raw_query`` — what users actually typed. An attacker
who searches "<offensive phrase>" repeatedly can pre-warm the global
autocomplete suggestion stream that EVERY other user sees. The
``trusted_autocomplete_queries`` helper here filters that source to
suggestions that have been searched by enough distinct users that
single-actor influence drops below the noise floor.

Public API
──────────
  sanitize_query(raw, *, max_len=80) -> str
      Cap total length, strip control chars, escape LIKE wildcards.

  tokenize_safe(query, *, max_tokens=10, max_token_len=40,
                min_token_len=2) -> list[str]
      Whitespace split + per-token length cap + drop-short + drop-
      mostly-punctuation.

  trusted_autocomplete_queries(prefix, *, min_distinct_users=3,
                               limit=4) -> list[str]
      Returns SearchQuery rows that meet the trust threshold. Defeats
      single-actor autocomplete poisoning.

Limits are tunable from settings (search.SEARCH_*) so ops can tighten
without a redeploy.
"""
from __future__ import annotations

import re
from typing import List


# ─── Tunables (read from settings at call time) ───────────────────────

def _setting(name: str, default):
    try:
        from django.conf import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _max_query_chars() -> int:
    return int(_setting('SEARCH_MAX_QUERY_CHARS', 80))


def _max_tokens() -> int:
    return int(_setting('SEARCH_MAX_TOKENS', 10))


def _max_token_chars() -> int:
    return int(_setting('SEARCH_MAX_TOKEN_CHARS', 40))


def _min_token_chars() -> int:
    return int(_setting('SEARCH_MIN_TOKEN_CHARS', 2))


# ─── Patterns ──────────────────────────────────────────────────────────

# Control characters and non-printables. Stripping them BEFORE the
# LIKE-escape step avoids accidentally escaping zero-width characters
# that wouldn't be printable anyway.
_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f]')

# Characters that are special to SQL LIKE: % (any sequence) and
# _ (any single char). Backslash needs to escape itself too.
# We escape with backslash; Django uses backslash as the LIKE escape
# character by default. (Postgres: ESCAPE '\' — Django ORM emits this.)
_LIKE_SPECIALS = re.compile(r'([\\%_])')


def sanitize_query(raw: str, *, max_len: int | None = None) -> str:
    """Reduce an untrusted query string to a safe form.

    Steps:
      1. Coerce to str, treat None / non-str as empty.
      2. Truncate to ``max_len`` (default settings.SEARCH_MAX_QUERY_CHARS,
         80). Truncate BEFORE further work so adversarial million-char
         inputs don't consume memory.
      3. Strip control characters.
      4. Normalise consecutive whitespace to single space.
      5. Escape LIKE special chars (``%``, ``_``, ``\\``).

    Returns the sanitised string. Empty string if input is empty / not
    a string.
    """
    if raw is None:
        return ''
    if not isinstance(raw, str):
        try:
            raw = str(raw)
        except Exception:
            return ''
    cap = max_len if max_len is not None else _max_query_chars()
    s = raw[:cap]                       # truncate FIRST — cheap defence
    s = _CONTROL_RE.sub(' ', s)
    s = ' '.join(s.split())              # collapse whitespace
    s = _LIKE_SPECIALS.sub(r'\\\1', s)   # escape LIKE wildcards
    return s


def tokenize_safe(query: str, *,
                  max_tokens: int | None = None,
                  max_token_chars: int | None = None,
                  min_token_chars: int | None = None) -> List[str]:
    """Tokenise a sanitised query into safe-for-DB substrings.

    Drops tokens that are:
      • shorter than ``min_token_chars`` (default 2)
      • mostly punctuation (after LIKE-escaping, a token of all backslashes
        is meaningless)

    Caps at ``max_tokens`` tokens, each at ``max_token_chars`` chars.
    """
    if not query:
        return []

    max_t = max_tokens if max_tokens is not None else _max_tokens()
    max_c = max_token_chars if max_token_chars is not None else _max_token_chars()
    min_c = min_token_chars if min_token_chars is not None else _min_token_chars()

    out: List[str] = []
    for raw_tok in query.split():
        if len(out) >= max_t:
            break
        tok = raw_tok[:max_c]
        # Strip any leading/trailing escape-backslash leftovers from the
        # LIKE-escape pass so we don't search for "\"" literally.
        tok_stripped = tok.replace('\\', '')
        if len(tok_stripped) < min_c:
            continue
        # Mostly-punctuation token? (letters + digits < half the chars)
        alnum = sum(1 for c in tok_stripped if c.isalnum())
        if alnum < max(1, len(tok_stripped) // 2):
            continue
        out.append(tok)
    return out


# ─── Autocomplete poisoning defence ────────────────────────────────────

def trusted_autocomplete_queries(prefix: str, *,
                                 min_distinct_users: int = 3,
                                 limit: int = 4) -> List[str]:
    """Return SearchQuery.raw_query values starting with ``prefix`` that
    have been searched by ``min_distinct_users`` OR MORE distinct users.

    Without the distinct-user threshold, a single actor can pre-warm
    the global suggestion stream by hammering the same query (or a set
    of adversarial queries). The threshold raises the cost of poisoning
    from "one curl loop" to "coordinate N accounts" — by which point
    the abuse looks like fraud and trips other detection paths.

    Notes:
      • The query is filtered to results_count > 0 too — we don't want
        to suggest queries we've already returned zero for.
      • prefix is sanitised here too (same LIKE-escape logic) so a
        ``%a`` prefix doesn't degenerate into "match anything starting
        with anything-then-a".
    """
    if not prefix or len(prefix) < 2:
        return []
    safe_prefix = sanitize_query(prefix, max_len=40)
    if not safe_prefix:
        return []

    try:
        from django.db.models import Count
        from apps.ai_engine.models import SearchQuery
        qs = (
            SearchQuery.objects
            .filter(
                raw_query__istartswith=safe_prefix,
                results_count__gt=0,
            )
            .values('raw_query')
            .annotate(distinct_users=Count('user', distinct=True))
            .filter(distinct_users__gte=min_distinct_users)
            .order_by('-distinct_users')[:limit]
            .values_list('raw_query', flat=True)
        )
        return list(qs)
    except Exception:
        return []
