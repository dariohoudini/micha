"""
Carrier registry — single point that maps carrier code → adapter
instance. Production swaps in real DHLAdapter / FedExAdapter etc.
"""
from __future__ import annotations

from functools import lru_cache

from .base import CarrierAdapter
from .dev_stub import DevStubCarrier

# Production will register concrete adapters here:
#   from .dhl import DHLAdapter
#   from .fedex import FedExAdapter
_REGISTRY = {
    'dev_stub': DevStubCarrier,
}


@lru_cache(maxsize=16)
def get_carrier_adapter(code: str) -> CarrierAdapter:
    cls = _REGISTRY.get(code) or DevStubCarrier
    return cls()
