"""
apps/inbound_webhooks/replay_registry.py
────────────────────────────────────────

Maps (provider, event_type) → handler function for the replay path.

The decorator wraps a view's ``post()`` method, which is great for
HTTP reception but not directly callable for admin-triggered replay
(no request object, no DRF context, etc.). So handlers that want to
support replay register themselves here with a pure-function signature:

    from apps.inbound_webhooks.replay_registry import register_replay

    @register_replay('appypay', 'payment.confirmed')
    def replay_payment_confirmed(payload: dict) -> dict:
        # Same business logic as the view, but takes the parsed payload
        # directly and returns a JSON-safe result dict.
        ...
        return {'status': 'replayed_ok', 'order_id': order.id}

The same handler is typically called from the actual webhook view
too — the view becomes a thin wrapper that extracts the verified
payload and calls the handler. This is the only way to keep the
behaviour of "live event" and "replayed event" identical.

For event_types that haven't been registered, replay refuses with
a clear error — the operator can see that the replay path doesn't
exist for that flow.
"""
from __future__ import annotations

from typing import Callable, Optional


# Keyed by (provider, event_type). event_type='' matches a default
# fallback handler for the provider.
_REGISTRY: dict[tuple[str, str], Callable] = {}


def register_replay(provider: str, event_type: str = ''):
    """Decorator: register a function as the replay handler for
    (provider, event_type).

    Pass event_type='' to register a provider-wide fallback.
    """
    def deco(fn):
        _REGISTRY[(provider, event_type)] = fn
        return fn
    return deco


def get_replay_handler(provider: str, event_type: str = '') -> Optional[Callable]:
    """Look up the handler for an event. Falls back to provider-wide
    fallback if specific event_type not registered."""
    fn = _REGISTRY.get((provider, event_type))
    if fn is not None:
        return fn
    return _REGISTRY.get((provider, ''))


def all_registered() -> list[tuple[str, str]]:
    """For ops introspection — what replay paths exist?"""
    return sorted(_REGISTRY.keys())
