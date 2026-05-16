"""
apps/tax/models.py

Tax engine — same temporal-correctness story as FX. The question every
accountant will eventually ask: "what tax rate did we apply to that
refund last March?" cannot be answered by a single mutable rate field.

Four tables:

  TaxJurisdiction   Geographic scope. country_code + optional province_code.
                    Lookup falls back from province → country when a
                    province has no specific override.

  TaxRate (temporal) Per-jurisdiction rate row. UNIQUE-current constraint
                    ensures we never have two rows claiming to be "now"
                    for the same jurisdiction (mirrors FXRate design).

  TaxCategory       STANDARD / REDUCED / ZERO / EXEMPT. Per-jurisdiction
                    rate multiplier — REDUCED at 50% in jurisdiction X
                    can be REDUCED at 30% in jurisdiction Y. Optional;
                    products without a category get STANDARD.

  TaxCalculation    Append-only audit row per checkout/refund. Stores
                    the line-item breakdown, total_tax, applied rates,
                    ref back to order/refund. The forensic answer to
                    "show me the rates you used on this transaction".
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class TaxJurisdiction(models.Model):
    """A region for which we maintain rates. Country-level rows always
    exist (fallback); province-level rows override when present."""
    country_code = models.CharField(max_length=2, help_text='ISO 3166-1 alpha-2, e.g. AO')
    # Empty string = country-wide row. ISO 3166-2 sub-code when set, e.g. AO-LUA.
    province_code = models.CharField(max_length=6, blank=True, default='')
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['country_code', 'province_code'],
                name='uniq_jurisdiction_country_province',
            ),
        ]
        indexes = [
            models.Index(fields=['country_code', 'province_code']),
        ]
        ordering = ['country_code', 'province_code']

    def __str__(self):
        return f'{self.name} ({self.country_code}{"-"+self.province_code if self.province_code else ""})'


class TaxRateSource(models.TextChoices):
    MANUAL    = 'manual',    'Manual (admin-set)'
    REGULATOR = 'regulator', 'Regulator publication'
    IMPORT    = 'import',    'Imported from external feed'


class TaxRate(models.Model):
    """Temporal rate row per jurisdiction. The CURRENT rate is the row
    with valid_until IS NULL."""
    jurisdiction = models.ForeignKey(
        TaxJurisdiction, on_delete=models.CASCADE, related_name='rates',
    )
    name = models.CharField(max_length=40, default='VAT',
                            help_text='Display name, e.g. VAT / IVA')
    rate = models.DecimalField(max_digits=6, decimal_places=4,
                               help_text='As a fraction — 0.14 = 14%')
    source = models.CharField(max_length=12, choices=TaxRateSource.choices,
                              default=TaxRateSource.MANUAL)
    note = models.CharField(max_length=200, blank=True)

    valid_from  = models.DateTimeField(db_index=True)
    valid_until = models.DateTimeField(null=True, blank=True, db_index=True,
                                       help_text='NULL = currently in effect')

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['jurisdiction', 'valid_until']),
            models.Index(fields=['jurisdiction', 'valid_from']),
        ]
        constraints = [
            # Only one CURRENT rate per jurisdiction
            models.UniqueConstraint(
                fields=['jurisdiction'],
                condition=models.Q(valid_until__isnull=True),
                name='uniq_current_tax_rate',
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gte=0) & models.Q(rate__lte=1),
                name='tax_rate_in_range',
            ),
        ]


class TaxCategoryCode(models.TextChoices):
    STANDARD = 'STANDARD', 'Standard'
    REDUCED  = 'REDUCED',  'Reduced'
    ZERO     = 'ZERO',     'Zero-rated'
    EXEMPT   = 'EXEMPT',   'Exempt'


class TaxCategoryRule(models.Model):
    """Per-jurisdiction multiplier per category. REDUCED at 50% in one
    country can be REDUCED at 30% in another."""
    jurisdiction = models.ForeignKey(
        TaxJurisdiction, on_delete=models.CASCADE, related_name='category_rules',
    )
    category = models.CharField(max_length=10, choices=TaxCategoryCode.choices)
    # 1.0 = use full rate; 0.5 = half rate; 0.0 = zero-rated; -1 special-cases EXEMPT
    multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['jurisdiction', 'category'],
                name='uniq_jurisdiction_category',
            ),
        ]


class TaxCalculation(models.Model):
    """Append-only audit row per calculation. The answer to "show your work"
    when a regulator or auditor asks."""
    ref_type = models.CharField(max_length=40, db_index=True)
    ref_id   = models.CharField(max_length=80, db_index=True)

    ship_to_country = models.CharField(max_length=2)
    ship_to_province = models.CharField(max_length=6, blank=True)
    jurisdiction = models.ForeignKey(
        TaxJurisdiction, on_delete=models.PROTECT, related_name='+',
    )
    rate_applied = models.DecimalField(max_digits=6, decimal_places=4)
    tax_rate = models.ForeignKey(
        TaxRate, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )

    # The full breakdown of line items + their tax — preserved verbatim so a
    # future change to TaxRate doesn't retroactively alter this row's story.
    breakdown = models.JSONField(default=dict)
    total_taxable = models.DecimalField(max_digits=14, decimal_places=2)
    total_tax = models.DecimalField(max_digits=14, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['ref_type', 'ref_id']),
        ]
        ordering = ['-created_at']
