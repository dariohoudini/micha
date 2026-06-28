"""Celery jobs for accounting (doc CH10 month-end + daily controls)."""
from celery import shared_task


@shared_task(name='accounting.daily_reconciliation')
def daily_reconciliation():
    """Sub-ledger ↔ GL reconciliation (CH3/4/5)."""
    from . import services
    recons = services.reconcile_sub_ledgers()
    return {'ledgers': [(r.ledger, r.balanced) for r in recons]}


@shared_task(name='accounting.recognise_deferred_revenue')
def recognise_deferred_revenue():
    """Monthly straight-line deferred revenue recognition (CH14)."""
    from . import services
    return services.recognise_deferred_revenue()


@shared_task(name='accounting.amortise_capitalised')
def amortise_capitalised():
    """Monthly amortisation of capitalised development (CH19)."""
    from . import services
    return services.amortise_capitalised()


@shared_task(name='accounting.snapshot_financials')
def snapshot_financials():
    """Daily refresh of the current period's financial statements (CH24)."""
    from datetime import date
    from . import services
    snap = services.snapshot_financials(date.today().strftime('%Y-%m'))
    return {'period': snap.period, 'net_profit_cents': snap.net_profit_cents,
            'balanced': snap.trial_balance_balanced}
