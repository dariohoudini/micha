"""
apps/fx/feeds.py
─────────────────

Pluggable rate-source backends for the refresh worker.

Each feed implements:

  fetch(pairs) -> dict[(source, target)] -> Decimal

where ``pairs`` is an iterable of (source_currency, target_currency)
tuples the worker is interested in. A feed may return a subset (a
specific provider might not cover all our pairs); the worker just
updates what it gets and leaves the rest stale-detected.

Why this is its own module
───────────────────────────
The orchestration (task → update_rate with drift guard) is one
concern. Where the rate comes from is another — and varies by
deployment. Test environments use the stub feed; production uses
BNA + an external multi-currency feed; smoke tests can inject any
feed via dependency injection.

Current implementations
────────────────────────
  StubFeed         — returns a fixed dict; used by tests and as the
                     local-dev default when no provider is configured.
  BNAFeed          — placeholder for the Banco Nacional de Angola API.
                     Real integration deferred (needs BNA API
                     credentials + endpoint contract); raises
                     FeedNotConfigured at fetch time so the worker
                     skips it without crashing.
  ExternalFeed     — placeholder for a multi-currency provider
                     (exchangerate.host / OXR / fixer.io). Same
                     not-configured behaviour.

When wiring a real feed:
  1. Implement fetch().
  2. Add the FXRateSource enum value if new (existing: bna_api,
     external).
  3. Drop the FeedNotConfigured raise.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable

log = logging.getLogger(__name__)


class FeedError(Exception):
    pass


class FeedNotConfigured(FeedError):
    """The feed exists but isn't deploy-configured (no API key etc)."""


class RateFeed:
    """Abstract base. Subclass and implement fetch()."""

    name = 'unknown'

    def fetch(self, pairs: Iterable[tuple]) -> dict:
        raise NotImplementedError


# ─── Test / local-dev stub ────────────────────────────────────────────

class StubFeed(RateFeed):
    """Returns a fixed dict. Used for tests + as the local-dev default.

    Construct with a dict of {(source, target): rate}; fetch returns
    only those of the requested pairs that we have rates for.
    """
    name = 'stub'

    def __init__(self, rates: dict | None = None):
        self._rates = {
            (s.upper(), t.upper()): Decimal(str(r))
            for (s, t), r in (rates or {}).items()
        }

    def fetch(self, pairs):
        out = {}
        for s, t in pairs:
            key = (s.upper(), t.upper())
            if key in self._rates:
                out[key] = self._rates[key]
        return out


# ─── BNA — Banco Nacional de Angola (placeholder) ─────────────────────

class BNAFeed(RateFeed):
    """Banco Nacional de Angola official rates.

    Real implementation needs:
      • BNA published API endpoint or scrape URL
      • Auth pattern (token / IP allowlist / public)
      • Response schema → Decimal conversion

    Until that's wired, the worker calls fetch() and gets a clean
    FeedNotConfigured to skip — no crashing the refresh loop.
    """
    name = 'bna_api'

    def fetch(self, pairs):
        raise FeedNotConfigured(
            'BNA feed not configured: needs BNA_API_URL + auth wiring'
        )


# ─── External multi-currency feed (placeholder) ───────────────────────

class ExternalFeed(RateFeed):
    """exchangerate.host / OXR / fixer.io style.

    Same placeholder pattern as BNAFeed — raises FeedNotConfigured
    until the provider integration lands.
    """
    name = 'external'

    def fetch(self, pairs):
        raise FeedNotConfigured(
            'External feed not configured: needs FX_EXTERNAL_PROVIDER + API key'
        )


# ─── Resolver ─────────────────────────────────────────────────────────

def get_default_feeds() -> list:
    """Return the feeds the refresh worker should consult, in priority
    order. BNA preferred for AOA pairs; external feed covers anything
    BNA doesn't return.

    Override via settings.FX_FEED_CLASSES in tests / staging.
    """
    try:
        from django.conf import settings
        override = getattr(settings, 'FX_FEEDS', None)
        if override is not None:
            return list(override)
    except Exception:
        pass
    return [BNAFeed(), ExternalFeed()]
