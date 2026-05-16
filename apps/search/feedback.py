"""
apps/search/feedback.py

Relevance-feedback loop. Three pieces:

  1. log_event()  — append-only writer for SearchEvent rows. Called from the
                    /search/event/ endpoint and any spot that knows a user
                    just acted on a search result.

  2. recompute_query_boosts() — periodic aggregator. Walks recent SearchEvent
                    rows, scores each (query, product) pair, writes
                    QueryProductBoost rows. Old events decay exponentially.

  3. boosts_for_query() — fast read used by the search query. Returns a
                    {product_id: score} dict, cached for hot queries via
                    apps.core.cache_kit so we don't query Postgres on every
                    keystroke of /products/?search=…

Why decay matters: yesterday's clicks should outweigh year-old ones because
catalog content shifts, seasons change, last week's hot product may now be
out of stock. We use a 30-day half-life — every 30 days an event is half as
influential.
"""
from __future__ import annotations
import math
import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import SearchEvent, QueryProductBoost, SearchEventKind

log = logging.getLogger(__name__)


# Tuneable weights — higher = stronger signal that the product is relevant
# for the query.
KIND_WEIGHTS = {
    SearchEventKind.IMPRESSION: 0.0,   # impressions normalise the score; no boost
    SearchEventKind.CLICK:       1.0,
    SearchEventKind.CART:        4.0,
    SearchEventKind.PURCHASE:   10.0,
}
HALF_LIFE_DAYS = 30
# Only aggregate events from the last LOOKBACK_DAYS. Older signal is fully
# decayed away by then; querying it is just wasted IO.
LOOKBACK_DAYS = 180
# Minimum impressions before we trust the click-through rate. With <5 views,
# 1 click would otherwise produce CTR=1.0 which is noise.
MIN_IMPRESSIONS_FOR_CONFIDENCE = 5


def normalize_query(raw: str) -> str:
    """Stable normalization used for storage AND lookup. Must match what the
    search endpoint produces, so the same query string maps to the same row.
    Cheap, idempotent."""
    if not raw:
        return ''
    s = raw.strip().lower()
    # Collapse whitespace
    s = ' '.join(s.split())
    return s[:200]


def log_event(*, query: str, product_id, kind: str,
              position: Optional[int] = None, user=None,
              anon_token: str = '') -> Optional[SearchEvent]:
    """Append-only writer. Returns the created row or None on failure
    (never raises — telemetry must not block business actions)."""
    try:
        q = normalize_query(query)
        if not q:
            return None
        if kind not in {k.value for k in SearchEventKind}:
            return None
        return SearchEvent.objects.create(
            query_normalized=q,
            product_id=product_id,
            kind=kind,
            position=position,
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            anon_token=(anon_token or '')[:64],
        )
    except Exception as e:
        log.debug('search log_event failed: %s', e)
        return None


def _decay_weight(age_days: float) -> float:
    """Exponential decay with 30-day half-life. age_days=0 → 1.0; age_days=30 → 0.5."""
    return math.exp(-math.log(2) * age_days / HALF_LIFE_DAYS)


def recompute_query_boosts(query: Optional[str] = None,
                           min_events: int = 3) -> dict:
    """Aggregate SearchEvent → QueryProductBoost.

    If ``query`` is provided, only recompute that query. Otherwise: every
    query with activity in the lookback window.

    Sketch of the math:
      - For each (query, product), sum weighted events with decay
      - Normalise per query: divide each product's raw score by the max in
        that query → score lands in [0, 1]
      - Skip products with fewer than ``min_events`` total events (low conf)
    """
    cutoff = timezone.now() - timedelta(days=LOOKBACK_DAYS)
    base = SearchEvent.objects.filter(created_at__gte=cutoff)
    if query is not None:
        base = base.filter(query_normalized=normalize_query(query))

    # Identify queries that need recomputation
    queries = list(base.values_list('query_normalized', flat=True).distinct())
    if not queries:
        return {'queries': 0, 'rows_written': 0}

    rows_written = 0
    for q in queries:
        # Pull all events for this query in one go (bounded by LOOKBACK_DAYS).
        events = list(
            SearchEvent.objects
            .filter(query_normalized=q, created_at__gte=cutoff)
            .values('product_id', 'kind', 'position', 'created_at')
        )
        if not events:
            continue

        # Per-product raw scores + sample sizes
        now = timezone.now()
        raw: dict[int, float] = {}
        sample: dict[int, int] = {}
        impressions: dict[int, int] = {}
        for ev in events:
            pid = ev['product_id']
            age_days = (now - ev['created_at']).total_seconds() / 86400.0
            decay = _decay_weight(age_days)
            kind_w = KIND_WEIGHTS.get(ev['kind'], 0.0)
            # Position dampener — top-3 results would dominate without this
            # because users mostly click the first 3 regardless of relevance.
            # Boost the OUTSIZED behaviour: a click way down the list (pos 20)
            # is a much stronger relevance signal than position 1.
            pos = ev['position'] or 1
            position_boost = math.log1p(pos) / math.log1p(20)  # 1 at pos~20
            if ev['kind'] == SearchEventKind.CLICK and pos > 5:
                kind_w *= (1.0 + position_boost)
            raw[pid] = raw.get(pid, 0.0) + kind_w * decay
            sample[pid] = sample.get(pid, 0) + 1
            if ev['kind'] == SearchEventKind.IMPRESSION:
                impressions[pid] = impressions.get(pid, 0) + 1

        # Wilson-style confidence: dampen products with too few impressions.
        # If a product was clicked 1/1 times, that's not 100% — it's "we
        # don't know yet". Treat such low-confidence boosts as 0 until they
        # accumulate sample size.
        for pid in list(raw.keys()):
            if sample[pid] < min_events:
                raw[pid] = 0.0

        # Normalise to [0, 1] within this query
        max_raw = max(raw.values()) if raw else 0.0
        scored = {
            pid: (val / max_raw) if max_raw > 0 else 0.0
            for pid, val in raw.items()
        }

        # Upsert
        with transaction.atomic():
            # Clear stale rows for this query first (products that fell out
            # of the window entirely).
            QueryProductBoost.objects.filter(query_normalized=q).delete()
            QueryProductBoost.objects.bulk_create([
                QueryProductBoost(
                    query_normalized=q,
                    product_id=pid,
                    score=score,
                    sample_size=sample.get(pid, 0),
                )
                for pid, score in scored.items()
                if score > 0
            ])
            rows_written += len([s for s in scored.values() if s > 0])

        # Bust cache so next read picks up the new scores
        try:
            from apps.core.cache_kit import bump_tag
            bump_tag(f'search_boost:{q}')
        except Exception:
            pass

    return {'queries': len(queries), 'rows_written': rows_written}


def boosts_for_query(query: str) -> dict[int, float]:
    """Return {product_id: boost} for a query. Cached.

    Empty dict if no signal yet — the search query then degrades to pure BM25.
    """
    q = normalize_query(query)
    if not q:
        return {}
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('search_boost', [f'search_boost:{q}'], q)
        return cached_call(key, lambda: _load_boosts(q), ttl=300, swr_ttl=60)
    except Exception:
        return _load_boosts(q)


def _load_boosts(q: str) -> dict[int, float]:
    return dict(
        QueryProductBoost.objects
        .filter(query_normalized=q)
        .values_list('product_id', 'score')
    )
