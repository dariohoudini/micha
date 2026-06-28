"""
Dev / fallback carrier adapter. Returns deterministic stub responses
so the end-to-end pipeline can run without live carrier APIs.
"""
from __future__ import annotations

import json
import secrets
from decimal import Decimal

from .base import CarrierAdapter, LabelResponse, RateQuote, TrackingUpdate


class DevStubCarrier(CarrierAdapter):
    code = 'dev_stub'

    def quote(self, *, from_addr, to_addr, weight_kg, dimensions, declared_value):
        # Two services: express + economy.
        base = Decimal(str(weight_kg)) * Decimal('300')
        return [
            RateQuote(success=True, service_code='express',
                      estimated_cost=(base * Decimal('2')).quantize(Decimal('0.01')),
                      currency='AOA', min_transit_days=2, max_transit_days=4),
            RateQuote(success=True, service_code='standard',
                      estimated_cost=base.quantize(Decimal('0.01')),
                      currency='AOA', min_transit_days=5, max_transit_days=10),
        ]

    def create_label(self, *, service_code, from_addr, to_addr,
                     weight_kg, dimensions, declared_value, incoterm='DAP'):
        tn = 'DS' + secrets.token_hex(8).upper()
        return LabelResponse(
            success=True, tracking_number=tn,
            file_key=f'labels/dev_stub/{tn}.pdf',
            format='pdf',
            raw={'service': service_code, 'declared_value': str(declared_value)},
        )

    def parse_webhook(self, *, headers, body, body_text):
        try:
            payload = json.loads(body_text) if body_text else {}
        except Exception:
            payload = {}
        events = payload.get('events') or [payload]
        out = []
        for ev in events:
            raw = ev.get('status', 'unknown')
            norm = _normalise_raw(raw)
            out.append(TrackingUpdate(
                raw_status=raw, normalised_status=norm,
                location=ev.get('location', ''),
                occurred_at=ev.get('occurred_at', ''),
                carrier_event_id=ev.get('event_id', secrets.token_hex(6)),
                confidence=1.0,
            ))
        return out


# Very small heuristic mapping — production swaps a learnt classifier.
_RAW_MAP = {
    'created': 'label_created',
    'collected': 'picked_up',
    'in_transit': 'in_transit',
    'arrived_at_facility': 'in_transit',
    'customs': 'customs_clearance',
    'customs_held': 'customs_held',
    'out_for_delivery': 'out_for_delivery',
    'delivery_attempted': 'delivery_attempted',
    'delivered': 'delivered',
    'returned': 'returned_to_sender',
    'exception': 'exception',
}


def _normalise_raw(raw: str) -> str:
    if not raw:
        return 'in_transit'
    raw = raw.lower().replace(' ', '_')
    return _RAW_MAP.get(raw, 'in_transit')
