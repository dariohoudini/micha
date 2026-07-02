"""Celery jobs that keep Angola payments correct (doc CH20)."""
from celery import shared_task


@shared_task(name='payments_angola.reference_expiry_sweep')
def reference_expiry_sweep():
    """JOB 1 — expire unpaid references/bank transfers past TTL."""
    from . import services
    return services.expire_references()


@shared_task(name='payments_angola.settlement_reconciliation',
             soft_time_limit=1500, time_limit=1800)  # recon: 25/30 min
def settlement_reconciliation():
    """JOB 4 — APPYPAY three-way settlement match."""
    from . import services
    return services.reconcile_settlement_day()


@shared_task(name='payments_angola.cod_reconciliation')
def cod_reconciliation():
    """JOB 5 — three-way COD cash match + courier exposure."""
    from . import services
    return services.reconcile_cod_daily()


@shared_task(name='payments_angola.wallet_integrity_check')
def wallet_integrity_check():
    """JOB 6 — ledger sum == cached balance per wallet."""
    from . import services
    return services.check_wallet_integrity()


@shared_task(name='payments_angola.wallet_hold_expiry')
def wallet_hold_expiry():
    """JOB 7 — release expired split-payment wallet holds."""
    from . import services
    return services.release_split_holds()


@shared_task(name='payments_angola.dunning_runner')
def dunning_runner():
    """JOB 8 — reminder sequence + expiry."""
    from . import services
    return services.run_dunning()


@shared_task(name='payments_angola.snapshot_kpis')
def snapshot_kpis():
    from . import services
    snap = services.snapshot_payments_kpis()
    return {'date': str(snap.snapshot_date)}
