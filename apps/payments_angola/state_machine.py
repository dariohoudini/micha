"""
Payment state machine (doc CH2) — universal order-payment lifecycle.

A strict, enforced transition table. Transitions not in the table are
rejected and logged as anomalies. This is the single source of truth for
what a payment may do next, regardless of method.
"""

# Canonical states (doc CH2.1)
CREATED = 'created'
AWAITING_PAYMENT = 'awaiting_payment'
PROCESSING = 'processing'
AUTHORISED = 'authorised'
PAID = 'paid'
COD_PENDING = 'cod_pending'
COD_COLLECTED = 'cod_collected'
FAILED = 'failed'
EXPIRED = 'expired'
CANCELLED = 'cancelled'
REFUND_PENDING = 'refund_pending'
REFUNDED = 'refunded'
PARTIALLY_REFUNDED = 'partially_refunded'

STATE_CHOICES = [
    (CREATED, 'Created'),
    (AWAITING_PAYMENT, 'Awaiting payment'),
    (PROCESSING, 'Processing'),
    (AUTHORISED, 'Authorised'),
    (PAID, 'Paid'),
    (COD_PENDING, 'COD pending'),
    (COD_COLLECTED, 'COD collected'),
    (FAILED, 'Failed'),
    (EXPIRED, 'Expired'),
    (CANCELLED, 'Cancelled'),
    (REFUND_PENDING, 'Refund pending'),
    (REFUNDED, 'Refunded'),
    (PARTIALLY_REFUNDED, 'Partially refunded'),
]

# ALLOWED_TRANSITIONS (doc CH2.1, enforced). A FAILED/EXPIRED intent is
# terminal for retry purposes — a retry always creates a NEW flow, never
# reuses the failed one.
ALLOWED_TRANSITIONS = {
    CREATED: {AWAITING_PAYMENT, PROCESSING, COD_PENDING, CANCELLED},
    AWAITING_PAYMENT: {PROCESSING, PAID, EXPIRED, CANCELLED},
    PROCESSING: {PAID, AUTHORISED, FAILED},
    AUTHORISED: {PAID, CANCELLED},
    PAID: {REFUND_PENDING, PARTIALLY_REFUNDED},
    COD_PENDING: {COD_COLLECTED, CANCELLED, FAILED},
    COD_COLLECTED: {PAID},
    FAILED: set(),          # terminal — retry creates a new flow
    EXPIRED: set(),         # terminal
    CANCELLED: set(),       # terminal
    REFUND_PENDING: {REFUNDED, PARTIALLY_REFUNDED, FAILED},
    PARTIALLY_REFUNDED: {REFUND_PENDING, REFUNDED},
    REFUNDED: set(),        # terminal
}

# Terminal states that count as a successful collection of funds.
SUCCESS_STATES = {PAID, PARTIALLY_REFUNDED, REFUNDED}
# Method → expected happy-path (doc CH2 method→state mapping).
PREPAID_PATH = [CREATED, AWAITING_PAYMENT, PROCESSING, PAID]
COD_PATH = [CREATED, COD_PENDING, COD_COLLECTED, PAID]


class IllegalTransition(Exception):
    def __init__(self, frm, to):
        self.frm = frm
        self.to = to
        super().__init__(f'illegal payment transition {frm} → {to}')


def can_transition(frm, to):
    return to in ALLOWED_TRANSITIONS.get(frm, set())
