"""
apps/tax/service.py

Public entrypoints:

  resolve_jurisdiction(country, province=None)
      Returns the most-specific TaxJurisdiction row matching (country,
      province). Province match wins over country-only fallback.

  get_rate(jurisdiction, at=None)
      Returns the TaxRate row in effect at ``at`` (or now). Cached for
      current-rate lookups; historical lookups bypass the cache.

  calculate(line_items, *, ship_to_country, ship_to_province='',
            at=None, ref_type='', ref_id='', log=True)
      Returns a dict:
        {
          'jurisdiction_id', 'rate_applied', 'total_taxable', 'total_tax',
          'lines': [{line_id, taxable, tax, category, multiplier}],
        }
      Writes a TaxCalculation row when ``log=True``.

  update_rate(jurisdiction, rate, *, source, user=None, note='')
      Closes the current rate row and inserts a new one (mirrors FX pattern).

Line item shape passed to calculate():
    {'id': 'line-1', 'amount': Decimal('100.00'), 'category': 'STANDARD'}
  - id is opaque (typically OrderItem.pk); appears verbatim in the breakdown
  - amount is the *tax-exclusive* taxable amount for that line
  - category defaults to STANDARD when omitted

Why the engine is jurisdiction-driven (not per-line jurisdiction):
  All line items in one calculation share the same ship-to address.
  Per-line jurisdictions would be marketplace-cross-border (Alibaba scale)
  — out of scope for now. Easy to extend later: calculate() becomes a
  loop over per-line jurisdictions and aggregates the breakdown.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import logging

from django.db import transaction
from django.utils import timezone

from .models import (
    TaxJurisdiction, TaxRate, TaxCategoryRule, TaxCalculation,
    TaxCategoryCode, TaxRateSource,
)

log = logging.getLogger(__name__)


class TaxError(Exception):
    pass


class NoJurisdiction(TaxError):
    pass


class NoRate(TaxError):
    pass


# ─── Jurisdiction lookup ───────────────────────────────────────────────────

def resolve_jurisdiction(country: str, province: str = '') -> TaxJurisdiction:
    """Return the TaxJurisdiction matching (country, province).

    Province match preferred; falls back to country-only row. Raises
    NoJurisdiction if neither exists — caller decides whether to refuse
    the sale or zero-rate the transaction.
    """
    country = (country or '').upper()
    province = (province or '').upper()
    if not country:
        raise NoJurisdiction('country required')

    qs = TaxJurisdiction.objects.filter(country_code=country, is_active=True)
    if province:
        match = qs.filter(province_code=province).first()
        if match is not None:
            return match
    # Fall back to country-level row (province_code='')
    match = qs.filter(province_code='').first()
    if match is not None:
        return match
    raise NoJurisdiction(f'no jurisdiction for {country}{"/"+province if province else ""}')


# ─── Rate lookup ───────────────────────────────────────────────────────────

def get_rate(jurisdiction: TaxJurisdiction, *, at=None):
    """Return the TaxRate row in effect at ``at`` (or now). Mirrors the FX
    service: current rate cached, historical bypasses cache."""
    if at is None:
        return _get_current_cached(jurisdiction.id)
    return _get_at(jurisdiction.id, at)


def _get_current_cached(jurisdiction_id: int):
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('tax_rate', [f'tax:{jurisdiction_id}'], jurisdiction_id)
        rid = cached_call(key, lambda: _load_current_id(jurisdiction_id),
                          ttl=300, swr_ttl=60)
        if rid is None:
            return None
        return TaxRate.objects.filter(pk=rid).first()
    except Exception:
        return _get_at(jurisdiction_id, timezone.now())


def _load_current_id(jurisdiction_id):
    return (
        TaxRate.objects
        .filter(jurisdiction_id=jurisdiction_id, valid_until__isnull=True)
        .values_list('id', flat=True)
        .first()
    )


def _get_at(jurisdiction_id, at):
    from django.db.models import Q
    return (
        TaxRate.objects
        .filter(jurisdiction_id=jurisdiction_id, valid_from__lte=at)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=at))
        .order_by('-valid_from')
        .first()
    )


# ─── Calculation ───────────────────────────────────────────────────────────

def calculate(line_items: list, *,
              ship_to_country: str, ship_to_province: str = '',
              at=None, ref_type: str = '', ref_id: str = '',
              log_calc: bool = True) -> dict:
    """Compute tax for a set of line items shipping to a given destination.

    Raises NoJurisdiction or NoRate when the destination isn't covered.
    Callers (checkout) should handle this gracefully — typically by either
    refusing the sale, zero-rating it, or surfacing the issue to ops.
    """
    if not line_items:
        return _empty_result(ship_to_country, ship_to_province)

    jurisdiction = resolve_jurisdiction(ship_to_country, ship_to_province)
    rate_row = get_rate(jurisdiction, at=at)
    if rate_row is None:
        raise NoRate(f'no tax rate for {jurisdiction}')

    rate = Decimal(str(rate_row.rate))

    # Category multipliers — one lookup, cached implicitly per-jurisdiction
    category_rules = {
        r.category: Decimal(str(r.multiplier))
        for r in TaxCategoryRule.objects.filter(jurisdiction=jurisdiction)
    }
    # STANDARD defaults to 1.0 unless explicitly overridden
    category_rules.setdefault(TaxCategoryCode.STANDARD, Decimal('1.0'))

    line_breakdown = []
    total_taxable = Decimal('0')
    total_tax = Decimal('0')

    for item in line_items:
        amount = Decimal(str(item.get('amount') or '0'))
        if amount < 0:
            continue
        category = (item.get('category') or TaxCategoryCode.STANDARD).upper()
        # EXEMPT skips taxation entirely (not even visible on the invoice line)
        if category == TaxCategoryCode.EXEMPT:
            line_breakdown.append({
                'line_id': item.get('id', ''),
                'taxable': str(amount), 'tax': '0.00',
                'category': category, 'multiplier': '0',
            })
            continue

        multiplier = category_rules.get(category, Decimal('1.0'))
        effective_rate = rate * multiplier
        line_tax = (amount * effective_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )

        line_breakdown.append({
            'line_id': item.get('id', ''),
            'taxable': str(amount),
            'tax': str(line_tax),
            'category': category,
            'multiplier': str(multiplier),
        })
        total_taxable += amount
        total_tax += line_tax

    result = {
        'jurisdiction_id': jurisdiction.id,
        'jurisdiction_name': jurisdiction.name,
        'rate_applied': str(rate),
        'tax_rate_id': rate_row.id,
        'total_taxable': str(total_taxable.quantize(Decimal('0.01'))),
        'total_tax': str(total_tax.quantize(Decimal('0.01'))),
        'lines': line_breakdown,
    }

    if log_calc and ref_type and ref_id:
        try:
            TaxCalculation.objects.create(
                ref_type=ref_type[:40], ref_id=str(ref_id)[:80],
                ship_to_country=ship_to_country.upper(),
                ship_to_province=(ship_to_province or '').upper()[:6],
                jurisdiction=jurisdiction, rate_applied=rate, tax_rate=rate_row,
                breakdown=result, total_taxable=total_taxable,
                total_tax=total_tax,
            )
        except Exception as e:
            log.debug('tax calc audit failed: %s', e)

    return result


def _empty_result(country, province):
    return {
        'jurisdiction_id': None, 'jurisdiction_name': '',
        'rate_applied': '0', 'tax_rate_id': None,
        'total_taxable': '0.00', 'total_tax': '0.00',
        'lines': [],
    }


# ─── Rate updates ──────────────────────────────────────────────────────────

def update_rate(*, jurisdiction: TaxJurisdiction, rate, source: str = TaxRateSource.MANUAL,
                user=None, note: str = '', name: str = 'VAT') -> TaxRate:
    """Close the current rate row and insert a new one. Atomic — the
    UNIQUE-current partial index guards against double-open."""
    rate = Decimal(str(rate))
    if rate < 0 or rate > 1:
        raise TaxError('rate must be a fraction between 0 and 1')

    now = timezone.now()
    with transaction.atomic():
        TaxRate.objects.filter(
            jurisdiction=jurisdiction, valid_until__isnull=True,
        ).update(valid_until=now)

        new_row = TaxRate.objects.create(
            jurisdiction=jurisdiction, name=name[:40], rate=rate,
            source=source, note=note[:200], valid_from=now,
            recorded_by=user if (user and getattr(user, 'is_authenticated', False)) else None,
        )

    # Invalidate cache for this jurisdiction
    try:
        from apps.core.cache_kit import bump_tag
        bump_tag(f'tax:{jurisdiction.id}')
    except Exception:
        pass

    # Outbox event so analytics + seller webhooks can react to rate changes
    try:
        from apps.outbox.service import publish
        publish(
            topic='tax.rate_updated',
            payload={
                'jurisdiction_id': jurisdiction.id,
                'country_code': jurisdiction.country_code,
                'province_code': jurisdiction.province_code,
                'rate': str(rate), 'source': source,
            },
            dedupe_key=f'tax.rate_updated:{new_row.id}',
            ref_type='tax_rate', ref_id=str(new_row.id),
        )
    except Exception:
        pass

    return new_row
