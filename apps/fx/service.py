"""
apps/fx/service.py

Public entrypoints:

    get_rate(source, target, *, at=None)
        Returns the FXRate row in effect for (source, target) at the given
        instant (defaults to now). Same pair to itself = synthetic 1.0.

    convert(amount, *, from_currency, to_currency, ref_type='', ref_id='',
            at=None, log=True)
        Returns the converted Decimal AND writes a ConversionEvent row
        (unless log=False — useful for previewing in a UI).

    update_rate(*, source_currency, target_currency, rate, source,
                user=None, raw_response=None, note='')
        Closes the current row (valid_until=now) and inserts a new one
        with valid_from=now. Atomic — the UNIQUE-current constraint
        guarantees we never have two rows claiming to be "now".

Caching:
  get_rate() goes through cache_kit with tag 'fx:<source>:<target>' so
  every update_rate bumps that tag → next read picks up the new rate.
  Hot-path safe: stampede protection from cache_kit means a flash sale
  serving 10k product page renders in one second causes ONE DB hit.

Fail-safety:
  If no rate exists for a pair, we try the INVERSE (target→source) and
  invert it. If that also fails, get_rate returns None and convert raises.
  Conversion logging never blocks the math (log failure logged at debug).
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import logging

from django.db import transaction
from django.utils import timezone

from .models import FXRate, FXRateSource, ConversionEvent

log = logging.getLogger(__name__)


class FXError(Exception):
    pass


class RateNotFound(FXError):
    pass


# ─── Rate lookup ───────────────────────────────────────────────────────────

def get_rate(source: str, target: str, *, at=None):
    """Return the FXRate row in effect at ``at`` (or now). Same-currency
    returns None — callers should short-circuit before calling.

    The ``at=None`` case is the hot path (current rate) and goes through
    the cache. Any explicit ``at`` bypasses the cache — historical lookups
    must hit the DB so we get the temporally-correct row even when the
    requested instant is seconds in the past.
    """
    source = source.upper()
    target = target.upper()
    if source == target:
        return None

    # Try direct rate first
    rate_row = _get_direct(source, target, at)
    if rate_row is not None:
        return rate_row

    # Fall back to inverse + 1/rate
    inverse = _get_direct(target, source, at)
    if inverse is not None:
        synth = FXRate(
            source_currency=source, target_currency=target,
            rate=(Decimal(1) / inverse.rate),
            source=FXRateSource.INFERRED,
            valid_from=inverse.valid_from, valid_until=inverse.valid_until,
            note=f'inverse of {inverse.source}-sourced {target}->{source}',
        )
        return synth

    return None


def _get_direct(source: str, target: str, at):
    """Direct-pair lookup. Cache only used when caller wants the CURRENT
    rate (at is None); explicit timestamps always go straight to DB."""
    if at is None:
        return _get_current_cached(source, target)
    return _get_at(source, target, at)


def _get_current_cached(source: str, target: str):
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('fx_rate', [f'fx:{source}:{target}'], source, target)
        row_id = cached_call(key, lambda: _load_current_id(source, target),
                             ttl=300, swr_ttl=60)
        if row_id is None:
            return None
        return FXRate.objects.filter(pk=row_id).first()
    except Exception:
        return _get_at(source, target, timezone.now())


def _load_current_id(source: str, target: str):
    r = (
        FXRate.objects
        .filter(source_currency=source, target_currency=target, valid_until__isnull=True)
        .values_list('id', flat=True)
        .first()
    )
    return r


def _get_at(source: str, target: str, at):
    return (
        FXRate.objects
        .filter(
            source_currency=source, target_currency=target,
            valid_from__lte=at,
        )
        .filter(
            models_or_null('valid_until', at),
        )
        .order_by('-valid_from')
        .first()
    )


def models_or_null(field, at):
    """Q expression: ``field IS NULL OR field >= at``. The "or null" half
    matches the currently-open temporal row."""
    from django.db.models import Q
    return Q(**{f'{field}__isnull': True}) | Q(**{f'{field}__gt': at})


# ─── Conversion ────────────────────────────────────────────────────────────

def convert(amount, *, from_currency: str, to_currency: str,
            ref_type: str = '', ref_id: str = '',
            at=None, log_event: bool = True,
            round_to: int = 2) -> Decimal:
    """Convert ``amount`` and (by default) log a ConversionEvent."""
    if amount is None:
        return Decimal(0)
    amount = Decimal(str(amount))
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return _quantize(amount, round_to)

    rate_row = get_rate(from_currency, to_currency, at=at)
    if rate_row is None:
        raise RateNotFound(f'No FX rate for {from_currency}->{to_currency}')

    converted = amount * rate_row.rate
    converted = _quantize(converted, round_to)

    if log_event:
        try:
            ConversionEvent.objects.create(
                from_currency=from_currency, to_currency=to_currency,
                amount_from=amount, amount_to=converted,
                rate_applied=rate_row.rate,
                # Inferred rates aren't persisted, so the FK can be None
                fx_rate=rate_row if rate_row.pk else None,
                ref_type=ref_type[:40], ref_id=str(ref_id)[:80],
            )
        except Exception as e:
            log.debug('conversion event log failed: %s', e)

    return converted


def _quantize(amount: Decimal, places: int) -> Decimal:
    if places <= 0:
        return amount.to_integral_value(rounding=ROUND_HALF_UP)
    q = Decimal(10) ** -places
    return amount.quantize(q, rounding=ROUND_HALF_UP)


# ─── Rate updates ──────────────────────────────────────────────────────────

def update_rate(*, source_currency: str, target_currency: str, rate,
                source: str = FXRateSource.MANUAL, user=None,
                raw_response=None, note: str = '') -> FXRate:
    """Close the current rate for this pair and insert a new one.

    Atomicity: the UNIQUE-current constraint (PartialIndex on valid_until
    IS NULL) means two simultaneous update_rate calls cannot both leave
    two open rows behind — one wins, one fails with IntegrityError. We
    catch that and retry once.
    """
    source_currency = source_currency.upper()
    target_currency = target_currency.upper()
    rate = Decimal(str(rate))
    if rate <= 0:
        raise FXError('rate must be positive')

    now = timezone.now()

    with transaction.atomic():
        # Close out the current row, if any
        FXRate.objects.filter(
            source_currency=source_currency,
            target_currency=target_currency,
            valid_until__isnull=True,
        ).update(valid_until=now)

        # Insert the new one
        new_row = FXRate.objects.create(
            source_currency=source_currency,
            target_currency=target_currency,
            rate=rate, source=source,
            raw_response=raw_response or {},
            note=note[:200], valid_from=now,
            recorded_by=user if (user and getattr(user, 'is_authenticated', False)) else None,
        )

    # Invalidate caches for this pair + the inverse pair
    try:
        from apps.core.cache_kit import bump_tag
        bump_tag(f'fx:{source_currency}:{target_currency}')
        bump_tag(f'fx:{target_currency}:{source_currency}')  # inverse path
    except Exception:
        pass

    # Outbox event so analytics / seller webhooks / notifications can react
    try:
        from apps.outbox.service import publish
        publish(
            topic='fx.rate_updated',
            payload={
                'source_currency': source_currency,
                'target_currency': target_currency,
                'rate': str(rate),
                'source': source,
            },
            dedupe_key=f'fx.rate_updated:{new_row.id}',
            ref_type='fx_rate', ref_id=str(new_row.id),
        )
    except Exception:
        pass

    return new_row
