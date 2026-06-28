"""
Abstract `CarrierAdapter` — every concrete carrier (DHL, FedEx,
DPD, Correios, La Poste, internal Choice) implements this small
interface. Caller code never talks to a carrier directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class RateQuote:
    success: bool
    service_code: str
    estimated_cost: Decimal
    currency: str
    min_transit_days: int
    max_transit_days: int
    error: str = ''


@dataclass
class LabelResponse:
    success: bool
    tracking_number: str
    file_key: str
    format: str
    raw: dict
    error: str = ''


@dataclass
class TrackingUpdate:
    raw_status: str
    normalised_status: str
    location: str
    occurred_at: str
    carrier_event_id: str
    confidence: float = 1.0


class CarrierAdapter(ABC):
    code = 'abstract'

    @abstractmethod
    def quote(self, *, from_addr: dict, to_addr: dict,
              weight_kg: Decimal, dimensions: dict,
              declared_value: Decimal) -> list[RateQuote]:
        ...

    @abstractmethod
    def create_label(self, *, service_code: str, from_addr: dict,
                     to_addr: dict, weight_kg: Decimal,
                     dimensions: dict, declared_value: Decimal,
                     incoterm: str = 'DAP') -> LabelResponse:
        ...

    @abstractmethod
    def parse_webhook(self, *, headers: dict, body: bytes,
                      body_text: str) -> list[TrackingUpdate]:
        ...
