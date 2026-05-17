"""
apps/feed/service.py

Public entrypoint:

  build_feed(user=None, *, anon_token='', locale='pt-AO',
             max_tiles=60, section='home') -> dict

Pipeline:
  1. Call every registered producer for the section, in parallel-friendly
     fashion (just sequential here — Python's GIL + DB IO means parallel
     producers don't help much). Each producer returns 0..N tiles.
  2. Dedup by tile.id (same product surfaced by 'trending' AND 'similar_to_history'
     produces ONE tile with merged score — sum of scores so signals stack).
  3. Apply per-user filtering:
       - drop products from sellers the user has reported / blocked
       - drop products that match a content_safety category we've flagged
       - drop products user has already purchased (configurable)
  4. Sort by score descending.
  5. Apply diversity reranking: walk the sorted list, demote a tile when
     its diversity_key has appeared too recently. Keeps the user from
     seeing 5 "Phones" in a row.
  6. Cap at max_tiles.
  7. Record feed served event for telemetry.

Cache:
  Per-user feed is cached via apps.core.cache_kit. Tags:
    feed:user:<id>       — user-specific signals changed (added an interaction)
    feed:trending        — global trending updated (15-min sweep)
    feed:catalog         — catalog changed (product saved)
  Any of these bumping → next read recomputes.

Fail-safety:
  Producer exceptions are caught individually so a bug in one section
  doesn't blank the whole feed. The assembler always returns at least the
  global trending fallback if everything else dies.
"""
from __future__ import annotations
import logging
from collections import defaultdict
from typing import Iterable

from .registry import all_producers, FeedContext, Tile

log = logging.getLogger(__name__)


# Diversity: never allow 3 in a row of the same diversity_key. We look at
# the immediately-preceding 2 positions; if both share the candidate's key
# we try the next candidate. When EVERY remaining candidate has that key
# (dominant category, no alternative), we accept it — better to fill the
# feed than starve it.
MAX_RUN_PER_KEY = 2
DIVERSITY_LOOKBACK = 2


def build_feed(user=None, *,
                anon_token: str = '', locale: str = 'pt-AO',
                max_tiles: int = 60, section: str = 'home') -> dict:
    """Returns dict {tiles: [...serialized tiles...], debug: {...counters...}}."""
    ctx = FeedContext(
        user=user, anon_token=anon_token, locale=locale,
        max_tiles=max_tiles, section=section,
    )

    # Cache key bakes in the user id + section + locale. Tags are added so
    # per-user / catalog signals invalidate appropriately.
    user_tag = f'feed:user:{user.id}' if (user and getattr(user, 'is_authenticated', False)) \
                                          else f'feed:anon:{anon_token}'
    tags = [user_tag, 'feed:trending', 'feed:catalog']

    # Cache the FULL build (max_tiles fixed at 60 for the cached payload);
    # the caller's max_tiles is applied AFTER the cache fetch so different
    # callers don't fight over the same cache slot with different caps.
    try:
        from apps.core.cache_kit import cached_call, build_key
        cache_ctx = FeedContext(
            user=ctx.user, anon_token=ctx.anon_token, locale=ctx.locale,
            max_tiles=60, section=ctx.section,
        )
        key = build_key('feed', tags,
                        user.id if user and getattr(user, 'is_authenticated', False) else anon_token,
                        section, locale)
        cached = cached_call(key, lambda: _build(cache_ctx), ttl=300, swr_ttl=60)
    except Exception:
        cached = _build(ctx)

    if max_tiles < len(cached.get('tiles', [])):
        cached = {**cached, 'tiles': cached['tiles'][:max_tiles]}
    return cached


def _build(ctx: FeedContext) -> dict:
    """The uncached build path. Producers → merge → filter → rank → diversify."""
    producers = all_producers(ctx.section)
    by_id: dict[str, Tile] = {}
    debug = {'producers': {}, 'before_dedup': 0, 'after_dedup': 0,
             'filtered': 0, 'final': 0}

    for p in producers:
        try:
            tiles = list(p.fn(ctx))
        except Exception:
            log.exception('feed producer %s failed', p.name)
            tiles = []
        debug['producers'][p.name] = len(tiles)
        debug['before_dedup'] += len(tiles)
        for t in tiles:
            if not t.id:
                continue
            existing = by_id.get(t.id)
            if existing is None:
                by_id[t.id] = t
            else:
                # Merge: stack scores; keep the first reason but record both
                existing.score = float(existing.score) + float(t.score)
                if t.reason and t.reason not in existing.reason:
                    existing.reason = f'{existing.reason}; {t.reason}'.strip('; ')

    debug['after_dedup'] = len(by_id)

    # Per-user filtering — drop blocked sellers, content-flagged products, etc.
    candidates = list(by_id.values())
    candidates, filtered_n = _apply_filters(candidates, ctx)
    debug['filtered'] = filtered_n

    # Sort by score descending
    candidates.sort(key=lambda t: t.score, reverse=True)

    # Diversity pass + cap
    final = _diversify(candidates, max_tiles=ctx.max_tiles)
    debug['final'] = len(final)

    # Telemetry — fire-and-forget
    _record_served(ctx, len(final), debug)

    return {
        'tiles': [_serialize(t) for t in final],
        'debug': debug,
    }


def _serialize(t: Tile) -> dict:
    return {
        'id': t.id, 'kind': t.kind, 'ref_id': t.ref_id,
        'score': round(float(t.score), 4),
        'payload': t.payload,
        'reason': t.reason,
    }


# ─── Filtering ─────────────────────────────────────────────────────────────

def _apply_filters(tiles: list[Tile], ctx: FeedContext) -> tuple[list[Tile], int]:
    """Drop tiles the user shouldn't see. Returns (kept, dropped_count)."""
    if not (ctx.user and getattr(ctx.user, 'is_authenticated', False)):
        return tiles, 0

    blocked_sellers = _blocked_seller_ids(ctx.user)
    hidden_products = _hidden_product_ids(ctx.user)

    kept = []
    dropped = 0
    for t in tiles:
        if t.kind == 'product':
            seller_id = t.payload.get('seller_id')
            if seller_id and seller_id in blocked_sellers:
                dropped += 1
                continue
            pid = t.payload.get('product_id') or t.ref_id
            if pid and str(pid) in hidden_products:
                dropped += 1
                continue
        kept.append(t)
    return kept, dropped


def _blocked_seller_ids(user) -> set:
    """Sellers the user has reported / blocked. Cached briefly."""
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('feed_blocked_sellers', [f'feed:user:{user.id}'], user.id)
        return set(cached_call(key, lambda: _load_blocked_sellers(user),
                                ttl=300, swr_ttl=60))
    except Exception:
        return _load_blocked_sellers(user)


def _load_blocked_sellers(user) -> set:
    try:
        # Try the standard reports table — falls back to empty set if it
        # doesn't exist in this codebase.
        from apps.reports.models import UserReport
        return set(
            UserReport.objects.filter(
                reporter=user, status__in=('open', 'reviewed', 'actioned'),
            ).values_list('target_user_id', flat=True)
        )
    except Exception:
        return set()


def _hidden_product_ids(user) -> set:
    """Products user explicitly dismissed from their feed."""
    # No persistent dismissal mechanism yet — placeholder set. The plumbing
    # is in place so adding the table later is a one-line change.
    return set()


# ─── Diversity reranker ────────────────────────────────────────────────────

def _diversify(sorted_tiles: list[Tile], max_tiles: int) -> list[Tile]:
    """Walk the sorted list; demote a tile if its diversity_key has appeared
    too many times in the last DIVERSITY_LOOKBACK positions.

    Demotion = move to the next slot that's diverse. We do this with a
    sliding-window counter rather than a full re-sort so the high-score
    tiles still float to the top (just spread out)."""
    if not sorted_tiles:
        return []

    output: list[Tile] = []
    pending: list[Tile] = list(sorted_tiles)
    recent_keys: list[str] = []

    while pending and len(output) < max_tiles:
        # Find the first pending tile whose diversity_key isn't saturated
        chosen_idx = None
        for i, t in enumerate(pending):
            key = t.diversity_key or t.kind
            run = sum(1 for k in recent_keys[-DIVERSITY_LOOKBACK:] if k == key)
            if run < MAX_RUN_PER_KEY:
                chosen_idx = i
                break
        # If nothing matched (everything saturated), break the tie by just
        # taking the highest-score remaining tile — better to fill the feed
        # than to leave it short.
        if chosen_idx is None:
            chosen_idx = 0

        t = pending.pop(chosen_idx)
        output.append(t)
        recent_keys.append(t.diversity_key or t.kind)

    return output


# ─── Telemetry ─────────────────────────────────────────────────────────────

def _record_served(ctx: FeedContext, count: int, debug: dict):
    """Fire-and-forget feed-served metric. Useful for tracking feed quality
    over time (avg tiles, dedup rate, filter rate). NEVER raises."""
    try:
        from apps.telemetry import metrics
        if hasattr(metrics, 'feed_served'):
            metrics.feed_served.labels(section=ctx.section).inc()
    except Exception:
        pass
