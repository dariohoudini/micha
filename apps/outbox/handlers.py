"""
Handler registry.

Apps register handlers by topic in their `outbox_handlers.py` module — that
file is auto-imported by OutboxConfig.ready().

    # apps/orders/outbox_handlers.py
    from apps.outbox.handlers import handler

    @handler('order.placed')
    def on_order_placed(payload):
        # do work — send email, fire webhook, etc.
        # Raise an exception to trigger retry; return normally on success.
        ...

A topic may have multiple handlers; all run in sequence and any failure
marks the event for retry. Handlers should be idempotent — they may run
more than once if the dispatcher crashes between executing the handler
and marking the event dispatched.
"""
from collections import defaultdict
from typing import Callable

_REGISTRY: dict[str, list[Callable]] = defaultdict(list)


def handler(topic):
    """Decorator: register a function as a handler for `topic`."""
    def deco(fn):
        _REGISTRY[topic].append(fn)
        return fn
    return deco


def get_handlers(topic):
    return list(_REGISTRY.get(topic, []))


def all_topics():
    return sorted(_REGISTRY.keys())
