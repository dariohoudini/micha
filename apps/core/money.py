"""
apps/core/money.py
==================

Central money helpers for an e-commerce app that handles real value.

Why this exists
─────────────────
Float arithmetic on money is the most common silent bug in commerce
codebases. Audit findings across the repo:

  • apps/payments/views.py:RequestPayoutView did
      wallet.debit(float(amount), ...)
    where wallet.balance is a Decimal. Decimal +/- float raises
    TypeError in Python 3 — would crash every real payout.
  • apps/ledger/service.py did float(amount_cents) / 100.0 — fine
    arithmetically, but injects float into the ledger which other
    code might then add to a Decimal balance.
  • apps/products/views.py coerced variant + price-tier prices via
    float() before storing on the cart row, so the cart's snapshot
    price drifted from the canonical Decimal in the catalog.
  • apps/fx/service.py used ROUND_HALF_UP for currency conversion,
    which systematically biases the platform up by fractions of a
    cent across millions of transactions.

Design
─────────
  • ``to_decimal(value)`` — universal safe coercion. Accepts int, str,
    float, Decimal, or None; returns a Decimal. Float passes through
    ``str()`` first to avoid binary-floating-point artifacts
    (Decimal(0.1) is 0.10000000000000000555..., Decimal(str(0.1))
    is 0.1).
  • ``quantize(value, places=2)`` — banker's rounding (HALF_EVEN).
    Banker's rounding is the IEEE 754 default and the accounting
    convention precisely because it doesn't systematically bias
    over many transactions: rounding 0.5 to even alternates up and
    down on average.
  • ``Money(amount, currency)`` — value-object wrapper. Refuses to
    add MoneyA + MoneyB when currencies differ. Stops the entire
    class of bug where "this is AOA" leaks into a USD calculation.
  • Currency precision is configurable per-currency (AOA = 2 dp,
    BTC = 8 dp, JPY = 0 dp). For now we hardcode AOA + USD; extend
    via CURRENCY_PRECISION as more are added.

This module replaces ad-hoc ``float(price)``, ``round(x, 2)``,
``Decimal(value)`` patterns throughout the codebase.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
from typing import Optional, Union


__all__ = [
    'to_decimal',
    'quantize',
    'add',
    'subtract',
    'multiply',
    'divide',
    'sum_decimals',
    'Money',
    'CurrencyMismatchError',
    'NEGATIVE_REJECTED',
    'CURRENCY_PRECISION',
    'DEFAULT_CURRENCY',
]


DEFAULT_CURRENCY = 'AOA'

# Decimal places per currency. Most cash-like currencies use 2;
# JPY/KRW use 0; crypto uses 8.
CURRENCY_PRECISION = {
    'AOA': 2,
    'USD': 2,
    'EUR': 2,
    'BRL': 2,
    'GBP': 2,
    'ZAR': 2,
    'JPY': 0,
    'KRW': 0,
    'BTC': 8,
}


# Sentinel for code that wants to assert "this value must be > 0".
class _NegativeRejected:
    def __repr__(self): return 'NEGATIVE_REJECTED'


NEGATIVE_REJECTED = _NegativeRejected()


# ─── Type alias for things that can be coerced to Decimal ─────────────────
DecimalLike = Union[int, str, float, Decimal, None]


# ─── Core helpers ─────────────────────────────────────────────────────────

def to_decimal(value: DecimalLike) -> Decimal:
    """Coerce any numeric input to a Decimal safely.

    The float → Decimal path goes via ``str()`` so we don't inherit
    binary-floating-point artifacts:

      Decimal(0.1)        → Decimal('0.1000000000000000055511151231...')
      Decimal(str(0.1))   → Decimal('0.1')        ← what callers expect

    Returns Decimal(0) on None / empty.
    """
    if value is None or value == '':
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # str() collapses binary float to its shortest decimal
        # representation; that's the value the user actually typed.
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            raise ValueError(f'cannot coerce {value!r} to Decimal')
    raise TypeError(f'cannot coerce {type(value).__name__} to Decimal')


def quantize(value: DecimalLike, *, places: int = 2,
             rounding=ROUND_HALF_EVEN) -> Decimal:
    """Quantize to the given decimal places using banker's rounding.

    Banker's rounding (HALF_EVEN) is the accounting convention
    because it doesn't systematically bias. ROUND_HALF_UP — the
    Python ``round()`` default in <3.0 and still common in business
    code — adds a fraction of a cent in the platform's favour over
    millions of transactions.

    Examples:
      quantize('100.005')   → Decimal('100.00')   # rounds to even
      quantize('100.015')   → Decimal('100.02')   # rounds to even
      quantize('100.025')   → Decimal('100.02')   # rounds to even
      quantize('100.035')   → Decimal('100.04')   # rounds to even
    """
    d = to_decimal(value)
    if places < 0:
        raise ValueError('places must be >= 0')
    q = Decimal(10) ** -places if places > 0 else Decimal(1)
    return d.quantize(q, rounding=rounding)


def add(*amounts: DecimalLike) -> Decimal:
    """Sum a sequence of values as Decimal."""
    total = Decimal(0)
    for a in amounts:
        total += to_decimal(a)
    return total


def subtract(a: DecimalLike, b: DecimalLike) -> Decimal:
    return to_decimal(a) - to_decimal(b)


def multiply(a: DecimalLike, b: DecimalLike) -> Decimal:
    return to_decimal(a) * to_decimal(b)


def divide(a: DecimalLike, b: DecimalLike, *, places: int = 2) -> Decimal:
    """Divide with banker's rounding at the given precision."""
    return quantize(to_decimal(a) / to_decimal(b), places=places)


def sum_decimals(iterable) -> Decimal:
    """Like ``sum()`` but starts at Decimal(0) so a sum of Decimals
    stays Decimal instead of coercing to float.
    """
    total = Decimal(0)
    for v in iterable:
        total += to_decimal(v)
    return total


# ─── Currency-aware Money value object ────────────────────────────────────

class CurrencyMismatchError(Exception):
    """Raised when two Money values with different currencies are combined."""


@dataclass(frozen=True)
class Money:
    """Immutable money value: amount + currency.

    Operations enforce currency identity — Money(100, 'AOA') + Money(5, 'USD')
    raises CurrencyMismatchError. Conversions must go through the FX
    service explicitly so the conversion is auditable.
    """
    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self):
        # The dataclass is frozen, but __post_init__ can assign via
        # object.__setattr__. We use it to normalise the amount to
        # the currency's precision so two Money instances compare
        # equal byte-for-byte if they represent the same value.
        normalised = quantize(
            self.amount, places=CURRENCY_PRECISION.get(self.currency, 2),
        )
        object.__setattr__(self, 'amount', normalised)

    @classmethod
    def of(cls, amount: DecimalLike, currency: str = DEFAULT_CURRENCY) -> 'Money':
        return cls(to_decimal(amount), currency)

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> 'Money':
        return cls(Decimal(0), currency)

    def _check(self, other: 'Money'):
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f'{self.currency} vs {other.currency}: cannot combine '
                f'different currencies. Convert via apps.fx.service first.'
            )

    def __add__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, scalar):
        return Money(self.amount * to_decimal(scalar), self.currency)

    __rmul__ = __mul__

    def __truediv__(self, scalar):
        return Money(
            (self.amount / to_decimal(scalar)).quantize(
                Decimal(10) ** -CURRENCY_PRECISION.get(self.currency, 2),
                rounding=ROUND_HALF_EVEN,
            ),
            self.currency,
        )

    def __neg__(self):
        return Money(-self.amount, self.currency)

    def __lt__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._check(other)
        return self.amount >= other.amount

    def is_positive(self) -> bool:
        return self.amount > 0

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_negative(self) -> bool:
        return self.amount < 0

    def abs(self) -> 'Money':
        return Money(abs(self.amount), self.currency)

    def as_str(self) -> str:
        return f'{self.amount} {self.currency}'

    def __str__(self):
        return self.as_str()
