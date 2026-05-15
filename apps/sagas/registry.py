"""
apps/sagas/registry.py

DSL for declaring sagas. Each saga is a named sequence of (action, compensate)
pairs. Both callables take ``(payload, saga)`` and may mutate payload in place
to pass data forward. ``compensate`` is optional — pure side-effects that have
no rollback (logging, idempotent notifications) just omit it.

A step may raise ``SagaWait`` to park the saga until a deadline; the runner
will status=waiting and return without compensating.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SagaStep:
    name: str
    action: Callable
    compensate: Optional[Callable] = None


@dataclass
class SagaDef:
    name: str
    steps: list[SagaStep] = field(default_factory=list)
    # Hard deadline for the whole saga. After this many seconds since creation
    # the recovery sweeper will mark it abandoned. None = no overall deadline.
    max_lifetime_seconds: Optional[int] = None


# Module-level registry. Populated by @register at import time.
_REGISTRY: dict[str, SagaDef] = {}


def register(saga_def: SagaDef):
    """Register a SagaDef. Idempotent — re-registration overwrites (helpful
    during dev / autoreload)."""
    _REGISTRY[saga_def.name] = saga_def
    return saga_def


def get(name: str) -> SagaDef:
    if name not in _REGISTRY:
        raise KeyError(f'No saga registered with name {name!r}. '
                       f'Known: {sorted(_REGISTRY.keys())}')
    return _REGISTRY[name]


def all_names() -> list[str]:
    return sorted(_REGISTRY.keys())


# ─── Signals ───────────────────────────────────────────────────────────────
class SagaWait(Exception):
    """Raise from a step to park the saga until ``until``. The runner sets
    status=waiting and persists ``wait_until``. Caller should ensure the
    saga is resumed by some external signal (webhook, scheduled task)."""
    def __init__(self, until, reason: str = ''):
        self.until = until
        self.reason = reason
        super().__init__(f'SagaWait until {until.isoformat()}: {reason}')


class SagaAbort(Exception):
    """Raise from a step to immediately move to compensation without
    treating the step as a "real" failure. Useful when a step decides the
    workflow should unwind for *business* reasons (e.g. fraud detected
    mid-flight), not because of a transient error."""
    pass
