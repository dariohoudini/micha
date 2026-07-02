"""Celery jobs for accounting (doc CH10 month-end + daily controls)."""
import logging

from celery import shared_task

log = logging.getLogger('audit')


@shared_task(name='accounting.verify_journal_chain',
             soft_time_limit=1500, time_limit=1800)
def verify_journal_chain():
    """Re-verify the JournalEntry hash chain end-to-end (Gap-Coverage CH7).

    Mirrors audit.verify_admin_chain: the financial journal is the money
    source of truth, so a broken chain = the evidence was altered — logged
    CRITICAL so the alert pipeline pages on-call with the exact seq.
    Generous own time budget (25/30 min): the walk re-hashes every entry
    plus its lines and grows with ledger volume.
    """
    from apps.core.audit_chain import verify_chain
    from .models import JournalEntry

    rows = (
        JournalEntry.objects
        .filter(seq__isnull=False)
        .order_by('seq')
        .prefetch_related('lines')
        .iterator(chunk_size=500)
    )
    result = verify_chain(rows)

    try:
        from apps.telemetry.metrics import audit_chain_intact, audit_chain_length
        audit_chain_intact.labels(log='journal_entry').set(1 if result['ok'] else 0)
        audit_chain_length.labels(log='journal_entry').set(result['count'])
    except Exception:
        log.debug('journal chain gauge publish failed', exc_info=True)

    if result['ok']:
        log.info('journal.chain_ok', extra={'log': 'journal_entry',
                                            'count': result['count']})
    else:
        log.critical('journal.chain_broken',
                     extra={'log': 'journal_entry', **result})
    return result


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
