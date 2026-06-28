"""
Stock state machine (doc CH2). Every unit is in exactly one of these
mutually-exclusive states; the sum equals the physical total. Transitions
are atomic DB operations validated against the invariant.
"""

AVAILABLE = 'available'
RESERVED = 'reserved'
COMMITTED = 'committed'
IN_TRANSIT = 'in_transit'
DAMAGED = 'damaged'
RETURNED = 'returned'

STATES = [AVAILABLE, RESERVED, COMMITTED, IN_TRANSIT, DAMAGED, RETURNED]

# Each maps to a quantity counter column on InventorySku.
STATE_FIELD = {s: f'{s}_quantity' for s in STATES}

# Valid transitions (doc CH2.1). `removed` and `inbound` are pseudo-states:
# removed decrements total (delivered/written-off); inbound increments it.
VALID_TRANSITIONS = {
    AVAILABLE: {RESERVED, DAMAGED},
    RESERVED: {COMMITTED, AVAILABLE},
    COMMITTED: {IN_TRANSIT, AVAILABLE},        # cancel before ship → available
    IN_TRANSIT: {'removed', RETURNED},          # delivered or return-in-transit
    RETURNED: {AVAILABLE, DAMAGED},
    DAMAGED: {'removed'},                        # written off
}


class InsufficientStock(Exception):
    def __init__(self, state, requested, available=None, sku_id=None):
        self.state = state
        self.requested = requested
        self.available = available
        self.sku_id = sku_id
        super().__init__(
            f'insufficient {state}: requested {requested}, have {available}')


class StockLockContention(Exception):
    """The SKU row is locked by another transaction (no_wait fast-fail)."""


class IllegalStockTransition(Exception):
    def __init__(self, frm, to):
        super().__init__(f'illegal stock transition {frm} → {to}')


def can_transition(frm, to):
    return to in VALID_TRANSITIONS.get(frm, set())
