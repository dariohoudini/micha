"""Ledger reconciliation beat tasks.

Periodic invariant checks for the source-of-truth ledger:

  ledger.check_invariants        — every 5 min, updates Prometheus
                                    gauges for global imbalance +
                                    unbalanced-journal count.

  ledger.reconcile_cached        — hourly, scans cached counters
                                    (User.store_credit, loyalty_points,
                                    SellerWallet.balance) against the
                                    ledger and updates a drift gauge.
                                    NEVER auto-corrects; ops decides.
"""
import logging

from celery import shared_task
from apps.core.task_locks import singleton_task


log = logging.getLogger(__name__)


@shared_task(name='ledger.check_invariants')
@singleton_task('beat:ledger.check_invariants')
def check_invariants():
    """Cheap invariant checks + gauge refresh. Runs every 5 minutes.

    Two queries:
      • Global Σ debits vs Σ credits — must be 0.
      • Per-journal balance — must always be empty (post() enforces).

    Any non-zero result alerts via Prometheus. Specific journals get
    surfaced via the admin /api/v1/admin/ledger/health/ endpoint.
    """
    from . import reconciliation
    try:
        from apps.telemetry.metrics import (
            ledger_imbalance_cents,
            ledger_unbalanced_journals,
        )

        global_result = reconciliation.check_global_invariant()
        unbalanced = reconciliation.find_unbalanced_journals(limit=100)

        # AOA is the canonical currency. If we later support multi-currency
        # imbalance per currency, group by Account.currency here.
        ledger_imbalance_cents.labels(currency='AOA').set(
            global_result.imbalance_cents,
        )
        ledger_unbalanced_journals.set(len(unbalanced))

        # Log a structured warning if anything is off so the on-call
        # gets a fast lead even without Prometheus.
        if not global_result.is_balanced or unbalanced:
            log.error(
                'ledger.invariants: imbalance=%d unbalanced_journals=%d',
                global_result.imbalance_cents, len(unbalanced),
            )
            for j in unbalanced[:5]:
                log.error(
                    '  unbalanced journal id=%s key=%s imbalance=%d ref=%s/%s',
                    j.journal_id, j.idempotency_key, j.imbalance_cents,
                    j.ref_type, j.ref_id,
                )

        return {
            'imbalance_cents': global_result.imbalance_cents,
            'unbalanced_journals': len(unbalanced),
            'debit_total': global_result.debit_total_cents,
            'credit_total': global_result.credit_total_cents,
        }
    except Exception:
        log.exception('ledger.check_invariants failed')
        return {'error': True}


@shared_task(name='ledger.reconcile_cached')
@singleton_task('beat:ledger.reconcile_cached')
def reconcile_cached():
    """Hourly: scan cached counters against the ledger.

    NEVER auto-corrects. Reconciliation correction is a deliberate
    operator decision (the ledger could be wrong, in which case
    rewriting cached counters would compound the error). This task
    SURFACES drift; an admin endpoint applies the correction.

    Limits the scan to users with non-zero cached balances — drift on
    a zero balance is impossible (any non-zero ledger entry was
    matched by a non-zero cached value).
    """
    from . import reconciliation
    try:
        from apps.telemetry.metrics import (
            ledger_cached_counter_drift_count,
            ledger_cached_counter_drift_cents,
        )

        result = reconciliation.scan_user_drift(
            batch_size=500, max_users=50_000,
        )

        ledger_cached_counter_drift_count.set(result['drift_count'])
        ledger_cached_counter_drift_cents.set(result['total_drift_cents'])

        if result['drift_count'] > 0:
            log.error(
                'ledger.reconcile_cached: drift detected on %d counter(s), '
                'total %d cents drift; sample: %s',
                result['drift_count'], result['total_drift_cents'],
                result['sample'][:5],
            )

        return result
    except Exception:
        log.exception('ledger.reconcile_cached failed')
        return {'error': True}
