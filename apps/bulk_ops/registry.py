"""
apps/bulk_ops/registry.py

DSL for declaring bulk-op handlers. Auto-discovered from each app's
``bulk_handlers.py`` module.

A handler is a function ``(item_ref, params, request_user) -> dict``:
  - Receives the stringified item PK, the job's params, and the user who
    requested the job (for audit attribution).
  - Returns a dict on success. The dict is stored on BulkJobItem.result.
  - Returns ``{'skipped': True, 'reason': ...}`` to mark the item skipped
    (e.g. item already in target state — bulk-suspend of an already-suspended
    user is a no-op, not an error).
  - Raises on failure. The exception is captured into BulkJobItem.error.

Idempotency: handlers MUST be safe to retry. The worker re-runs items
that were stuck in `processing` (e.g. worker crash mid-handler), so
running the same handler twice must not double-execute side effects.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class BulkHandler:
    name: str
    fn: Callable
    # Optional audit-log action name. If set, every successful item also
    # writes an AdminActionLog row (composes with admin audit decorator).
    audit_action: Optional[str] = None
    description: str = ''


_REGISTRY: dict[str, BulkHandler] = {}


def register(handler: BulkHandler):
    _REGISTRY[handler.name] = handler
    return handler


def get(name: str) -> BulkHandler:
    if name not in _REGISTRY:
        raise KeyError(f'No bulk handler registered for {name!r}. '
                       f'Known: {sorted(_REGISTRY.keys())}')
    return _REGISTRY[name]


def all_names() -> list[str]:
    return sorted(_REGISTRY.keys())
