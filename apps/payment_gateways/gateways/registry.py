"""
Gateway registry — single point that decides "which gateway handles
this currency / market". Production swaps providers by editing
settings.PAYMENT_GATEWAY_ROUTING; no code change.
"""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from .base import PaymentGateway
from .dev_stub import DevStubGateway
from .multicaixa import MulticaixaGateway
from .stripe import StripeGateway


_REGISTRY = {
    'multicaixa_express': MulticaixaGateway,
    'stripe':              StripeGateway,
    'dev_stub':            DevStubGateway,
}


@lru_cache(maxsize=8)
def get_gateway(name: str) -> PaymentGateway:
    cls = _REGISTRY.get(name)
    if not cls:
        raise ValueError(f'Unknown gateway: {name}')
    return cls()


def select_gateway_for(*, currency: str, country: str = '') -> PaymentGateway:
    """Route by currency first, then by country override.

    Default routing:
      AOA → Multicaixa Express
      USD / EUR / GBP / BRL → Stripe
      anything else → dev_stub

    Overridable via settings.PAYMENT_GATEWAY_ROUTING (dict of
    "<CCY>" or "<CCY>:<COUNTRY>" → gateway name).
    """
    routing = getattr(settings, 'PAYMENT_GATEWAY_ROUTING', {}) or {}
    key_specific = f'{currency.upper()}:{country.upper()}'
    if key_specific in routing:
        return get_gateway(routing[key_specific])
    if currency.upper() in routing:
        return get_gateway(routing[currency.upper()])
    if currency.upper() == 'AOA':
        return get_gateway('multicaixa_express')
    if currency.upper() in ('USD', 'EUR', 'GBP', 'BRL'):
        return get_gateway('stripe')
    return get_gateway('dev_stub')
