"""Seed the IFRS chart of accounts (doc CH1.1) on first migrate."""
from django.db import migrations


def seed(apps, schema_editor):
    GLAccount = apps.get_model('accounting', 'GLAccount')
    from apps.accounting.chart_of_accounts import CHART_OF_ACCOUNTS
    for code, name, typ, nb in CHART_OF_ACCOUNTS:
        GLAccount.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': typ,
                      'normal_balance': nb})


def unseed(apps, schema_editor):
    # Keep accounts on reverse — they may have posted lines (PROTECT).
    pass


class Migration(migrations.Migration):
    dependencies = [('accounting', '0001_initial')]
    operations = [migrations.RunPython(seed, unseed)]
