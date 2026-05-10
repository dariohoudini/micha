"""
Product search engine — single source of truth.

What this fixes
---------------
Before this module, MICHA had two search paths:
  • apps/products/views.py  — Q(title__icontains=...) (slow, no diacritic folding)
  • apps/search/views.py    — SearchVector at query time (slow, no GIN index)
…and the frontend was calling the worse one.

Now both sides go through `search_products(qs, raw_query)`, which:
  • Lowercases + folds diacritics (so "telemovel" matches "telemóvel")
  • Expands a small synonym map (so "telefone" also finds "telemóvel")
  • Uses the GIN-indexed `search_vector` column when running on Postgres
  • Falls back to LIKE on SQLite (dev only — never production)

Synonyms are deliberately kept minimal — they're high-leverage when
correct and dangerous when wrong. The list grows as we observe queries
that fail to retrieve obvious matches.
"""
import re
import unicodedata
from typing import Iterable

from django.db import connection
from django.db.models import F, Q


# ── Synonym map ──────────────────────────────────────────────────────────
# Direction-symmetric: any token in the list is rewritten to ALL of them.
# All tokens lowercase, diacritic-free.
_SYNONYM_GROUPS = [
    {'telemovel', 'telefone', 'celular', 'smartphone', 'phone'},
    {'tenis', 'sapatilha', 'sneaker'},
    {'capulana', 'pano', 'wax'},
    {'computador', 'pc', 'laptop', 'portatil'},
    {'tv', 'televisao', 'televisor'},
    {'auscultador', 'fone', 'headphone', 'auricular'},
    {'crianca', 'menino', 'menina', 'bebe', 'kid', 'baby'},
    {'mulher', 'feminino', 'senhora'},
    {'homem', 'masculino', 'cavalheiro'},
]
_SYNONYM_INDEX: dict[str, list[str]] = {}
for group in _SYNONYM_GROUPS:
    for token in group:
        _SYNONYM_INDEX[token] = sorted(group - {token})


_TOKEN_SPLIT_RE = re.compile(r'[\s,;./_+\-]+')


def _fold(text: str) -> str:
    """Lowercase + diacritic-fold (NFKD)."""
    text = (text or '').lower()
    text = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in text if not unicodedata.combining(c))


def normalize_query(raw: str) -> tuple[list[str], list[str]]:
    """Return (primary_tokens, expanded_tokens).

    primary_tokens: what the user typed (folded, deduped, length-capped).
    expanded_tokens: synonyms of primary tokens that are NOT in primary.
    """
    folded = _fold(raw or '')[:200]
    raw_tokens = [t for t in _TOKEN_SPLIT_RE.split(folded) if len(t) >= 2]
    seen = set()
    primary: list[str] = []
    for t in raw_tokens:
        if t not in seen:
            seen.add(t)
            primary.append(t)

    expanded: list[str] = []
    for t in primary:
        for syn in _SYNONYM_INDEX.get(t, ()):
            if syn not in seen:
                seen.add(syn)
                expanded.append(syn)
    return primary, expanded


def _is_postgres() -> bool:
    return connection.vendor == 'postgresql'


def _record_search_metric(start, has_results: bool):
    try:
        import time as _time
        from apps.telemetry.metrics import search_queries, search_latency
        search_queries.labels(has_results='yes' if has_results else 'no').inc()
        search_latency.observe(_time.monotonic() - start)
    except Exception:
        pass


def search_products(queryset, raw_query: str):
    """Filter `queryset` by `raw_query` with relevance ranking.

    On Postgres: uses the GIN-indexed `search_vector` column with weighted
    rank. The query is folded via `unaccent` so "telemovel" hits "telemóvel".
    Synonyms are OR'd into the tsquery.

    On SQLite (dev): falls back to LIKE across folded title+brand+description
    so devs can at least search.

    Returns the filtered queryset (annotated with `_rank` on Postgres so
    callers can `order_by('-_rank')`).
    """
    import time as _time
    _start = _time.monotonic()
    primary, expanded = normalize_query(raw_query)
    if not primary:
        return queryset

    if _is_postgres():
        from django.contrib.postgres.search import SearchQuery, SearchRank

        # Build "primary | synonym | synonym | …" — favour primary terms via &
        # in the multi-token case so two-word queries narrow rather than widen.
        # We keep it simple here (OR everything) which is more recall-friendly.
        all_terms = primary + expanded
        # Quote each term so weird chars don't blow up the parser
        ts_query_str = ' | '.join(f"'{t}':*" for t in all_terms)
        try:
            sq = SearchQuery(ts_query_str, search_type='raw', config='simple')
        except Exception:
            # Older Postgres or restricted role — fall back to plain
            sq = SearchQuery(' '.join(all_terms))

        result = (
            queryset
            .annotate(_rank=SearchRank(F('search_vector'), sq))
            .filter(search_vector=sq)
            .order_by('-_rank')
        )
        # Note: has_results determined at iteration time. We approximate by checking exists()
        # cheaply; the rank index makes this fast.
        try:
            _record_search_metric(_start, result.exists())
        except Exception:
            pass
        return result

    # SQLite fallback (dev only). LIKE on raw fields can't fold diacritics
    # at DB level, so we filter in Python after fetching candidate rows.
    # This is fine for dev (small datasets); production runs Postgres.
    candidates = list(queryset[:1000])  # cap so a buggy dev DB can't OOM
    matches = []
    for p in candidates:
        haystack = _fold(' '.join([p.title or '', p.brand or '', p.description or '']))
        for term in primary + expanded:
            if term in haystack:
                matches.append(p)
                break
    _record_search_metric(_start, bool(matches))
    if not matches:
        return queryset.none()
    return queryset.filter(pk__in=[p.pk for p in matches])


def compute_search_vector(product):
    """Build the SearchVector value for a single product. Used by signal + backfill."""
    if not _is_postgres():
        return None
    from django.contrib.postgres.search import SearchVector
    from django.db.models import Value
    # Diacritic-fold each field at index time so the stored vector contains
    # both the original and the folded form.
    parts = []
    parts.append(SearchVector(Value(_fold(product.title or '')), weight='A'))
    if product.brand:
        parts.append(SearchVector(Value(_fold(product.brand)), weight='B'))
    if getattr(product, 'category', None) and product.category:
        parts.append(SearchVector(Value(_fold(product.category.name or '')), weight='B'))
    parts.append(SearchVector(Value(_fold(product.description or '')), weight='C'))
    # Tags
    try:
        tag_text = ' '.join(t.name for t in product.tags.all())
    except Exception:
        tag_text = ''
    if tag_text:
        parts.append(SearchVector(Value(_fold(tag_text)), weight='B'))

    combined = parts[0]
    for v in parts[1:]:
        combined = combined + v
    return combined


def update_search_vector(product):
    """Recompute and persist `search_vector` for a single product (Postgres only)."""
    if not _is_postgres():
        return
    from django.db.models import F as _F
    from .models import Product
    vector = compute_search_vector(product)
    if vector is None:
        return
    Product.objects.filter(pk=product.pk).update(search_vector=vector)
