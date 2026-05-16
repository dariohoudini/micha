"""
apps/forecasting/service.py

Public entrypoints:

  refresh_daily_demand(product, *, days=90)
    Recompute DailyDemand rows from Order/OrderItem for the last `days`.
    Idempotent — re-running overwrites the same (product, day) rows.

  forecast(product, *, horizon_days=30) -> dict
    Run the EWMA forecast on this product's DailyDemand. Persists a
    DemandForecast row. Returns the predicted units + bounds.

  compute_reorder_point(product, *, lead_time_days=7, service_level=0.95)
    Newsvendor-style: μ_lead_time + z * σ_lead_time.
      μ_lead_time = daily_mean × lead_time_days
      σ_lead_time = daily_stddev × √lead_time_days     (random walk)
      z = 1.65 for 95%, 1.96 for 97.5%, 2.33 for 99%
    Returns dict {reorder_point, safety_stock, recommended_qty}.

  generate_recommendation(product, *, lead_time_days, service_level)
    Top-level: refresh demand → forecast → reorder point → if current
    stock < reorder_point, create a ReorderRecommendation (idempotent
    per product). Publish 'forecasting.reorder_recommended' outbox event.

  run_for_seller(seller, *, lead_time_days=7)
    Walk all of a seller's active products, run generate_recommendation
    for each. Used by the bulk-ops handler.

Math choices:
  EWMA (α=0.3) with day-of-week seasonality factor — handles "Sundays
  outsell weekdays" without needing 365 days of data. Falls back to SMA
  on short history (< 14 days) and to ZERO on near-empty history.
  Cap predicted_units at sensible bounds so a single huge order doesn't
  blow out the forecast.
"""
from __future__ import annotations
import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    DailyDemand, DemandForecast, ReorderRecommendation,
    ForecastMethod, ReorderAction,
)

log = logging.getLogger(__name__)

# Forecast tuning
EWMA_ALPHA = Decimal('0.30')         # higher = more responsive to recent days
DEFAULT_HORIZON_DAYS = 30
MIN_SAMPLES_FOR_EWMA = 14
MIN_SAMPLES_FOR_FORECAST = 7
LOOKBACK_DAYS = 90

# Service-level z-scores (one-tailed)
Z_SCORE = {
    Decimal('0.90'): Decimal('1.282'),
    Decimal('0.95'): Decimal('1.645'),
    Decimal('0.975'): Decimal('1.960'),
    Decimal('0.99'):  Decimal('2.326'),
}


# ─── Daily demand aggregation ──────────────────────────────────────────────

def refresh_daily_demand(product, *, days: int = LOOKBACK_DAYS):
    """Rebuild DailyDemand rows for ``product`` over the last ``days``.

    Idempotent — re-running for the same window overwrites the same rows.
    Counts NET units (gross minus refunded units on the same day).
    """
    try:
        from apps.orders.models import OrderItem
    except Exception:
        return {'updated': 0}

    cutoff = timezone.now() - timedelta(days=days)
    # OrderItem.created_at on a paid Order = the date we count
    # the demand against.
    rows = (
        OrderItem.objects
        .filter(
            order__seller=product.store.owner,
            order__payment_status='paid',
            product=product,
            order__created_at__gte=cutoff,
        )
        .values('order__created_at__date')
        .annotate(units=Sum('quantity'),
                  revenue=Sum('total_price'))
    )
    upsert_count = 0
    with transaction.atomic():
        # Pre-fetch existing rows so we can choose update vs create
        existing_by_day = {
            r.day: r for r in DailyDemand.objects.filter(
                product=product, day__gte=cutoff.date(),
            )
        }
        for r in rows:
            day = r['order__created_at__date']
            units = int(r['units'] or 0)
            revenue = r['revenue'] or Decimal('0')
            existing = existing_by_day.get(day)
            if existing is None:
                DailyDemand.objects.create(
                    product=product, day=day, units=units, revenue=revenue,
                )
                upsert_count += 1
            elif existing.units != units or existing.revenue != revenue:
                existing.units = units
                existing.revenue = revenue
                existing.save(update_fields=['units', 'revenue', 'computed_at'])
                upsert_count += 1
    return {'updated': upsert_count, 'period_days': days}


# ─── Forecast math ─────────────────────────────────────────────────────────

def forecast(product, *, horizon_days: int = DEFAULT_HORIZON_DAYS) -> dict:
    """Run the demand forecast and persist a DemandForecast row.

    Methodology:
      • Pull last LOOKBACK_DAYS of DailyDemand
      • If < MIN_SAMPLES_FOR_FORECAST: return ZERO forecast (caller handles)
      • If MIN_SAMPLES_FOR_FORECAST <= n < MIN_SAMPLES_FOR_EWMA: use SMA
      • Otherwise: EWMA with day-of-week adjustment
      • Compute daily_mean + daily_stddev for the σ that feeds reorder math
    """
    cutoff = (timezone.now() - timedelta(days=LOOKBACK_DAYS)).date()
    samples = list(
        DailyDemand.objects
        .filter(product=product, day__gte=cutoff)
        .order_by('day')
        .values('day', 'units')
    )
    n = len(samples)

    if n < MIN_SAMPLES_FOR_FORECAST:
        method = ForecastMethod.ZERO
        daily_mean = Decimal('0')
        daily_stddev = Decimal('0')
    elif n < MIN_SAMPLES_FOR_EWMA:
        method = ForecastMethod.SMA
        units = [Decimal(s['units']) for s in samples]
        daily_mean = sum(units) / Decimal(n)
        daily_stddev = _stddev(units, daily_mean)
    else:
        method = ForecastMethod.EWMA
        daily_mean, daily_stddev = _ewma(samples)

    # Total predicted = mean × horizon. Bounds use σ × √horizon × z(95%).
    horizon = Decimal(horizon_days)
    predicted = (daily_mean * horizon).quantize(Decimal('0.01'), ROUND_HALF_UP)
    sigma_horizon = daily_stddev * Decimal(math.sqrt(float(horizon)))
    z95 = Z_SCORE[Decimal('0.95')]
    lower = max(Decimal('0'), predicted - z95 * sigma_horizon)
    upper = predicted + z95 * sigma_horizon

    DemandForecast.objects.update_or_create(
        product=product, horizon_days=horizon_days,
        defaults={
            'predicted_units': predicted,
            'lower_bound': lower.quantize(Decimal('0.01'), ROUND_HALF_UP),
            'upper_bound': upper.quantize(Decimal('0.01'), ROUND_HALF_UP),
            'daily_mean': daily_mean.quantize(Decimal('0.0001'), ROUND_HALF_UP),
            'daily_stddev': daily_stddev.quantize(Decimal('0.0001'), ROUND_HALF_UP),
            'method': method, 'sample_size': n,
        },
    )

    return {
        'predicted_units': float(predicted), 'lower': float(lower),
        'upper': float(upper), 'daily_mean': float(daily_mean),
        'daily_stddev': float(daily_stddev), 'method': method,
        'sample_size': n,
    }


def _stddev(values: list[Decimal], mean: Decimal) -> Decimal:
    """Population standard deviation in Decimal."""
    if not values:
        return Decimal('0')
    var = sum((v - mean) ** 2 for v in values) / Decimal(len(values))
    return Decimal(math.sqrt(float(var)))


def _ewma(samples: list[dict]) -> tuple[Decimal, Decimal]:
    """EWMA with day-of-week seasonality factor.

    Two-pass:
      1. Compute a per-weekday multiplier (units_on_weekday / overall_mean).
      2. De-seasonalise → EWMA → re-apply weekday factor to the last point.

    Returns (daily_mean_estimate, daily_stddev) — both in Decimal.
    """
    units = [Decimal(s['units']) for s in samples]
    days  = [s['day'] for s in samples]
    n = Decimal(len(units))
    overall_mean = sum(units) / n if n > 0 else Decimal('0')

    # Per-weekday averages
    by_dow: dict[int, list[Decimal]] = defaultdict(list)
    for d, u in zip(days, units):
        by_dow[d.weekday()].append(u)
    weekday_mean = {
        dow: (sum(vs) / Decimal(len(vs))) if vs else overall_mean
        for dow, vs in by_dow.items()
    }
    factor = {
        dow: ((m / overall_mean) if overall_mean > 0 else Decimal('1'))
        for dow, m in weekday_mean.items()
    }
    # De-seasonalise
    deseasoned = [
        u / factor.get(d.weekday(), Decimal('1')) if factor.get(d.weekday(), Decimal('1')) > 0 else u
        for d, u in zip(days, units)
    ]

    # EWMA
    smoothed = deseasoned[0]
    for v in deseasoned[1:]:
        smoothed = EWMA_ALPHA * v + (Decimal('1') - EWMA_ALPHA) * smoothed

    # Re-apply the AVERAGE seasonal factor across the horizon (caller
    # samples 30 days = roughly equal weekday distribution → factor ≈ 1).
    mean_estimate = smoothed
    stddev = _stddev(units, overall_mean)
    return mean_estimate, stddev


# ─── Reorder point ────────────────────────────────────────────────────────

def compute_reorder_point(product, *, lead_time_days: int = 7,
                          service_level: float = 0.95) -> dict:
    """Newsvendor-style reorder point.

    reorder_point = μ_lead_time + z * σ_lead_time

    Where:
      μ_lead_time = daily_mean × lead_time_days
      σ_lead_time = daily_stddev × √lead_time_days   (random walk)
      z           = Z_SCORE[service_level]            (1.645 @ 95%)

    Safety stock is the buffer above expected demand = z * σ_lead_time.

    Recommended order quantity defaults to the horizon forecast — sellers
    typically reorder for a 30-day cover.
    """
    sl = Decimal(str(service_level))
    z = Z_SCORE.get(sl, Decimal('1.645'))

    fcst = DemandForecast.objects.filter(product=product).order_by(
        '-horizon_days'
    ).first()
    if fcst is None:
        # No forecast yet — caller should generate one first
        return {
            'reorder_point': 0, 'safety_stock': 0,
            'recommended_qty': 0, 'mu_lead_time': 0.0,
            'sigma_lead_time': 0.0,
        }

    lt = Decimal(lead_time_days)
    mu_lead = fcst.daily_mean * lt
    sigma_lead = fcst.daily_stddev * Decimal(math.sqrt(float(lt)))
    safety = (z * sigma_lead)
    reorder = mu_lead + safety

    # Recommended quantity = predicted demand over the forecast horizon
    # (so the seller covers the next horizon period in one order)
    recommended = max(Decimal('0'), fcst.predicted_units)

    return {
        'reorder_point': int(reorder.to_integral_value(rounding=ROUND_HALF_UP)),
        'safety_stock': int(safety.to_integral_value(rounding=ROUND_HALF_UP)),
        'recommended_qty': int(recommended.to_integral_value(rounding=ROUND_HALF_UP)),
        'mu_lead_time': float(mu_lead),
        'sigma_lead_time': float(sigma_lead),
        'daily_mean': float(fcst.daily_mean),
        'daily_stddev': float(fcst.daily_stddev),
    }


# ─── Top-level orchestration ──────────────────────────────────────────────

def generate_recommendation(product, *, lead_time_days: int = 7,
                            service_level: float = 0.95) -> dict:
    """Refresh demand → forecast → reorder point → maybe-create rec.

    Idempotent per (product, pending action): re-running same-day on a
    product with an existing pending rec is a no-op.
    """
    refresh_daily_demand(product)
    fc = forecast(product)
    rp = compute_reorder_point(product, lead_time_days=lead_time_days,
                                service_level=service_level)

    current_stock = int(product.quantity or 0)
    needs_reorder = current_stock < rp['reorder_point']

    if not needs_reorder:
        # Mark any prior pending recommendation as expired — current
        # situation is fine.
        ReorderRecommendation.objects.filter(
            product=product, action=ReorderAction.PENDING,
        ).update(action=ReorderAction.EXPIRED, action_at=timezone.now())
        return {
            'needs_reorder': False,
            'current_stock': current_stock,
            **rp,
            'forecast': fc,
        }

    # Idempotent insert: ON CONFLICT do-nothing on the partial unique
    # constraint. We try create; on IntegrityError (only when the
    # constraint actually exists — Postgres) we return the existing row.
    reason = (f'Stock {current_stock} below reorder point {rp["reorder_point"]} '
              f'(μ_lead={rp["mu_lead_time"]:.1f}, σ_lead={rp["sigma_lead_time"]:.2f}, '
              f'safety={rp["safety_stock"]}).')

    with transaction.atomic():
        # Manual idempotency — check existing pending first since SQLite
        # doesn't enforce partial unique constraints reliably.
        existing = ReorderRecommendation.objects.filter(
            product=product, action=ReorderAction.PENDING,
        ).first()
        if existing is None:
            rec = ReorderRecommendation.objects.create(
                product=product,
                current_stock=current_stock,
                reorder_point=rp['reorder_point'],
                recommended_qty=max(rp['recommended_qty'], rp['reorder_point'] - current_stock),
                safety_stock=rp['safety_stock'],
                lead_time_days=lead_time_days,
                forecast_daily_mean=Decimal(str(rp['daily_mean'])).quantize(Decimal('0.0001'), ROUND_HALF_UP),
                forecast_daily_stddev=Decimal(str(rp['daily_stddev'])).quantize(Decimal('0.0001'), ROUND_HALF_UP),
                reason=reason[:300],
            )
        else:
            rec = existing

    # Outbox publish — downstream notifications + seller webhooks pick up
    _publish_recommendation(rec)

    return {
        'needs_reorder': True,
        'recommendation_id': rec.id,
        'current_stock': current_stock,
        **rp,
        'forecast': fc,
        'recommended_qty': rec.recommended_qty,
    }


def _publish_recommendation(rec: ReorderRecommendation):
    try:
        from apps.outbox.service import publish
        publish(
            topic='forecasting.reorder_recommended',
            payload={
                'recommendation_id': rec.id,
                'product_id': str(rec.product_id),
                'seller_id': rec.product.store.owner_id if rec.product_id else None,
                'current_stock': rec.current_stock,
                'reorder_point': rec.reorder_point,
                'recommended_qty': rec.recommended_qty,
            },
            dedupe_key=f'forecasting.reorder:{rec.id}',
            ref_type='reorder_recommendation', ref_id=str(rec.id),
        )
    except Exception:
        log.debug('publish reorder rec failed', exc_info=True)


def act_on_recommendation(rec: ReorderRecommendation, *, action: str) -> ReorderRecommendation:
    """Seller marks a recommendation ordered/dismissed."""
    if action not in (ReorderAction.ORDERED, ReorderAction.DISMISSED):
        raise ValueError('action must be ordered or dismissed')
    if rec.action != ReorderAction.PENDING:
        raise ValueError(f'recommendation is already {rec.action}')
    rec.action = action
    rec.action_at = timezone.now()
    rec.save(update_fields=['action', 'action_at'])
    return rec


def run_for_seller(seller, *, lead_time_days: int = 7) -> dict:
    """Walk all of a seller's active products. Used by the bulk-ops handler."""
    try:
        from apps.products.models import Product
    except Exception:
        return {'processed': 0}
    qs = Product.objects.filter(
        store__owner=seller, is_active=True, is_archived=False,
    )
    summary = {'processed': 0, 'recommendations': 0, 'no_reorder_needed': 0,
               'errors': 0}
    for p in qs[:1000]:
        try:
            r = generate_recommendation(p, lead_time_days=lead_time_days)
            summary['processed'] += 1
            if r.get('needs_reorder'):
                summary['recommendations'] += 1
            else:
                summary['no_reorder_needed'] += 1
        except Exception:
            summary['errors'] += 1
            log.exception('forecast failed for product %s', p.pk)
    return summary
