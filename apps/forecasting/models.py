"""
apps/forecasting/models.py

Demand forecasting + reorder recommendations.

Three tables:

  DailyDemand        Pre-aggregated daily unit-sales per product. Source
                     of truth for the forecast math. Beat-computed from
                     paid Order/OrderItem rows — avoids fan-out joins on
                     every forecast call. Rolling 180-day retention.

  DemandForecast     Snapshot of the most recent forecast. One row per
                     (product, horizon_days). Stamped on every recompute;
                     historical accuracy can be measured later by
                     comparing actuals to past forecasts.

  ReorderRecommendation  Suggestion produced when current_stock falls below
                     reorder_point. Sellers can accept (action='ordered')
                     or dismiss it (action='dismissed'); we never auto-order.
                     Idempotent per (product, generated date) — re-running
                     the engine doesn't stack duplicates.

Why DailyDemand instead of querying Orders live:
  • Orders has variable schema (refunds reversed, partial cancellations,
    multi-currency). DailyDemand normalises into "shipped & not refunded
    units per day". One source of truth for forecasting math.
  • 90 days × 10k products = 900k rows. With a unique constraint, that
    fits one index page per product. Querying live joins Order × OrderItem
    × Refund — 10× more IO.
  • Lets ops backfill / fix historical data without touching production
    Order rows.
"""
from datetime import date
from django.db import models


class DailyDemand(models.Model):
    """Pre-aggregated daily sales per product. Beat-computed nightly."""
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='daily_demand',
    )
    day = models.DateField(db_index=True)
    # Net units = sum(order_item.quantity) for orders shipped/delivered on
    # this day, minus units refunded after the fact. We never go negative;
    # a same-day refund just produces a 0-unit row (or no row).
    units = models.PositiveIntegerField(default=0)
    # Revenue is convenience; not used by the math but useful in seller
    # dashboards alongside unit counts.
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'day'],
                                    name='uniq_product_day'),
        ]
        indexes = [
            models.Index(fields=['product', '-day']),
            models.Index(fields=['day']),
        ]
        ordering = ['-day']


class ForecastMethod(models.TextChoices):
    EWMA = 'ewma', 'Exponentially weighted moving avg (with weekday seasonality)'
    SMA  = 'sma',  'Simple moving average'
    ZERO = 'zero', 'Zero (insufficient history)'


class DemandForecast(models.Model):
    """Latest demand forecast for a product over a fixed horizon."""
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='demand_forecasts',
    )
    horizon_days = models.PositiveSmallIntegerField(default=30)
    # Total predicted units over the next ``horizon_days``.
    predicted_units = models.DecimalField(max_digits=12, decimal_places=2)
    # Lower / upper bounds from σ × z-score at 95% confidence. Sellers use
    # the upper for "how much should I stock for the safe case?"
    lower_bound = models.DecimalField(max_digits=12, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=12, decimal_places=2)
    # Daily-level mean and σ — primary inputs to reorder_point.
    daily_mean = models.DecimalField(max_digits=10, decimal_places=4)
    daily_stddev = models.DecimalField(max_digits=10, decimal_places=4)
    method = models.CharField(max_length=8, choices=ForecastMethod.choices)
    sample_size = models.PositiveIntegerField(help_text='Days of history that fed this forecast')
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'horizon_days'],
                                    name='uniq_product_horizon'),
        ]
        indexes = [
            models.Index(fields=['product', '-generated_at']),
        ]


class ReorderAction(models.TextChoices):
    PENDING   = 'pending',   'Pending seller action'
    ORDERED   = 'ordered',   'Seller marked as ordered'
    DISMISSED = 'dismissed', 'Seller dismissed'
    EXPIRED   = 'expired',   'Expired (replaced by newer recommendation)'


class ReorderRecommendation(models.Model):
    """One actionable suggestion per (product, generated date). The
    recommendation engine runs daily; sellers act on the pending list."""
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='reorder_recommendations',
    )
    current_stock = models.PositiveIntegerField()
    reorder_point = models.PositiveIntegerField()
    recommended_qty = models.PositiveIntegerField()
    safety_stock = models.PositiveIntegerField()
    lead_time_days = models.PositiveSmallIntegerField(default=7)
    # Snapshot of the forecast that produced this recommendation — frozen
    # so a future forecast doesn't retroactively change the reason.
    forecast_daily_mean = models.DecimalField(max_digits=10, decimal_places=4)
    forecast_daily_stddev = models.DecimalField(max_digits=10, decimal_places=4)

    reason = models.CharField(max_length=300)
    action = models.CharField(
        max_length=10, choices=ReorderAction.choices,
        default=ReorderAction.PENDING, db_index=True,
    )
    action_at = models.DateTimeField(null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # One pending recommendation per product per generation day —
            # rerunning the engine same-day doesn't stack duplicates.
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(action='pending'),
                name='uniq_pending_recommendation_per_product',
            ),
        ]
        indexes = [
            models.Index(fields=['product', '-generated_at']),
            models.Index(fields=['action', '-generated_at']),
        ]
        ordering = ['-generated_at']
