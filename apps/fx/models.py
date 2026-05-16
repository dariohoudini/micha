"""
apps/fx/models.py

FX rate service. Three concerns, three tables:

  FXRate            Temporal — one row per (source, target, valid_from).
                    Only ONE row is "current" per pair (valid_until IS NULL).
                    Updates close the current row and insert a new one;
                    this preserves history so we can answer "what rate was
                    used on March 14?" even if we update rates daily.

  ConversionEvent   Append-only audit log of every conversion the system
                    performed. Pinpoints rate, ref to the business object
                    (order, payout, refund), and the amounts on both sides.
                    Without this, a year-end audit can't reconcile.

  Currency rows themselves live in apps.i18n.Currency — we don't duplicate.

Why temporal vs. snapshot:
  A naïve "exchange_rate_to_aoa on Currency" loses the past the moment
  it's overwritten. If a refund is processed against a 6-month-old order,
  it should use the rate at THE TIME OF THE ORDER, not today's rate. Same
  for tax reports, accounting, regulator inquiries.
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class FXRateSource(models.TextChoices):
    MANUAL    = 'manual',    'Manual (admin override)'
    BNA_API   = 'bna_api',   'BNA (Banco Nacional de Angola) API'
    EXTERNAL  = 'external',  'External feed (e.g. OXR, fixer.io)'
    INFERRED  = 'inferred',  'Inferred from inverse / cross-rate'


class FXRate(models.Model):
    """One row per (source_currency, target_currency, valid_from). The CURRENT
    rate for any pair is the row with valid_until IS NULL."""
    source_currency = models.CharField(max_length=5, db_index=True)
    target_currency = models.CharField(max_length=5, db_index=True)
    # The rate: 1 unit of source_currency = `rate` units of target_currency.
    rate = models.DecimalField(max_digits=20, decimal_places=8)

    source = models.CharField(max_length=12, choices=FXRateSource.choices)
    raw_response = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=200, blank=True)

    # Temporal bookkeeping
    valid_from  = models.DateTimeField(db_index=True)
    valid_until = models.DateTimeField(null=True, blank=True, db_index=True,
                                       help_text='NULL = currently in effect')

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fx_rates_recorded',
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Hot path: look up CURRENT rate for a pair
            models.Index(fields=['source_currency', 'target_currency', 'valid_until']),
            # Audit path: look up rate at a specific past time
            models.Index(fields=['source_currency', 'target_currency', 'valid_from']),
        ]
        constraints = [
            # Only one current rate per pair
            models.UniqueConstraint(
                fields=['source_currency', 'target_currency'],
                condition=models.Q(valid_until__isnull=True),
                name='uniq_current_fx_rate',
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gt=0),
                name='fx_rate_positive',
            ),
        ]

    def __str__(self):
        period = 'current' if self.valid_until is None else f'until {self.valid_until:%Y-%m-%d}'
        return f'{self.source_currency}->{self.target_currency} @ {self.rate} ({period})'


class ConversionEvent(models.Model):
    """Audit row per conversion performed. Lets us prove a year later
    exactly which rate was applied to which order."""
    from_currency = models.CharField(max_length=5, db_index=True)
    to_currency = models.CharField(max_length=5, db_index=True)
    amount_from = models.DecimalField(max_digits=20, decimal_places=8)
    amount_to = models.DecimalField(max_digits=20, decimal_places=8)
    rate_applied = models.DecimalField(max_digits=20, decimal_places=8)

    # Which rate row drove this conversion
    fx_rate = models.ForeignKey(
        FXRate, on_delete=models.PROTECT,
        related_name='conversion_events',
        null=True, blank=True,
    )

    # Free-form reference back to the business operation
    ref_type = models.CharField(max_length=40, blank=True, db_index=True)
    ref_id   = models.CharField(max_length=80, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['ref_type', 'ref_id']),
            models.Index(fields=['from_currency', 'to_currency', '-created_at']),
        ]

    def __str__(self):
        return f'{self.amount_from} {self.from_currency} → {self.amount_to} {self.to_currency}'
