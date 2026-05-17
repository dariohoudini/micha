"""
apps/feed/registry.py

Producer registry for personalized feed tiles. Each app contributes a
`feed_producers.py` module that registers one or more producers via
``register(Producer(...))``; the registry is auto-discovered on startup.

A producer is a function ``(ctx) -> list[Tile]`` where ctx is the
FeedContext (user, anon_token, locale, max_tiles_hint, …) and Tile is
the dataclass below. Producers should be PURE: same context → same
output, no side effects, no DB writes. They may do DB *reads* and
should aggressively bound their work (LIMIT 25 etc.) — the assembler
caps and re-ranks afterwards.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Tile:
    """One tile in the assembled feed."""
    # Stable identifier for telemetry + dedup. Format: "<kind>:<ref_id>".
    id: str
    kind: str  # 'product' | 'category' | 'banner' | 'saved_search_match' | 'tier_perk'
    ref_id: str = ''
    # Higher = better; assembler sorts descending. Producers should
    # normalise to roughly [0, 1].
    score: float = 0.0
    # Diversity buckets — used to enforce "no 3 same-category in a row".
    diversity_key: str = ''
    # Per-tile metadata bag — surfaced to the client (image url, title,
    # badge, etc.). Producers populate what their tile kind needs.
    payload: dict = field(default_factory=dict)
    # Human-readable reason for ops debugging / "Why am I seeing this?"
    reason: str = ''


@dataclass
class FeedContext:
    user: object = None          # User or None for anon
    anon_token: str = ''         # session hash for anonymous users
    locale: str = 'pt-AO'
    max_tiles: int = 60          # soft cap requested by caller
    section: str = 'home'        # 'home' | 'wishlist' | 'category:<slug>' etc.


@dataclass
class Producer:
    name: str
    fn: Callable                  # (FeedContext) -> list[Tile]
    # Where in the feed this producer wants to appear — soft hint, the
    # assembler may move tiles around for diversity.
    section: str = 'home'
    # Cache tag — when bumped, invalidates this producer's cached output.
    # E.g. trending bumps every 15 min via the recommendations task.
    cache_tag: str = ''


_REGISTRY: dict[str, Producer] = {}


def register(p: Producer):
    _REGISTRY[p.name] = p
    return p


def all_producers(section: str = 'home') -> list[Producer]:
    return [p for p in _REGISTRY.values() if p.section == section]


def get(name: str) -> Producer:
    return _REGISTRY[name]
