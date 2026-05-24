"""
R2: seed Angola's 14% IVA as the active current rate, plus STANDARD
TaxCategoryRule at multiplier 1.0.

Source: Decreto Presidencial n.º 180/19, Regime Geral do IVA.
Effective: 2019-10-01. Rate: 14% standard.

This migration is idempotent — if a jurisdiction/rate row already
exists it won't be duplicated. Safe to apply on top of any state.
"""
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    TaxJurisdiction = apps.get_model('tax', 'TaxJurisdiction')
    TaxRate = apps.get_model('tax', 'TaxRate')
    TaxCategoryRule = apps.get_model('tax', 'TaxCategoryRule')

    jur, _ = TaxJurisdiction.objects.get_or_create(
        country_code='AO', province_code='',
        defaults={'name': 'Angola', 'is_active': True},
    )

    # Only insert rate if no current rate exists for this jurisdiction.
    if not TaxRate.objects.filter(jurisdiction=jur, valid_until__isnull=True).exists():
        TaxRate.objects.create(
            jurisdiction=jur,
            name='IVA',
            rate=Decimal('0.1400'),
            source='regulator',
            note='Decreto Presidencial n.º 180/19 — 14% standard rate',
            valid_from=timezone.now(),
            valid_until=None,
        )

    # Category multipliers. STANDARD at 1.0 = full rate; REDUCED at
    # 0.5 = half rate (5% reduced rate used in some categories);
    # ZERO at 0.0 = zero-rated (essentials); EXEMPT at -1 = no IVA.
    for category, mult in (
        ('STANDARD', Decimal('1.00')),
        ('REDUCED',  Decimal('0.36')),  # ~5% of 14%
        ('ZERO',     Decimal('0.00')),
        ('EXEMPT',   Decimal('-1.00')),
    ):
        TaxCategoryRule.objects.update_or_create(
            jurisdiction=jur, category=category,
            defaults={'multiplier': mult},
        )


def backwards(apps, schema_editor):
    # Conservative: do nothing. Removing tax data retroactively would
    # invalidate historical TaxCalculation rows that PROTECT-FK against it.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tax', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
