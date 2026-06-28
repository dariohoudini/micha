"""Seller Operations automation (doc CH3/CH5/CH6/CH9/CH13/CH14/CH15/CH16/CH19/CH24)."""
from celery import shared_task


@shared_task(name='seller_operations.activate_due_scheduled_listings')
def activate_due_scheduled_listings():
    """CH3 — flip SCHEDULED -> ACTIVE when go-live time arrives (every 5 min)."""
    from . import services
    return services.activate_due_scheduled_listings()


@shared_task(name='seller_operations.evaluate_repricing_rules')
def evaluate_repricing_rules(frequency=None):
    """CH5 — apply automated repricing rules (hourly + daily)."""
    from . import services
    return services.evaluate_repricing_rules(frequency=frequency)


@shared_task(name='seller_operations.run_bulk_export')
def run_bulk_export(job_id):
    """CH6 — async packing-slip / order-export generation."""
    from . import services
    job = services.run_bulk_export(job_id)
    return {'job': str(job.id), 'status': job.status}


@shared_task(name='seller_operations.escalate_pending_refunds')
def escalate_pending_refunds():
    """CH9 — owner@48h, admin@72h escalation of pending refund approvals."""
    from . import services
    return services.escalate_pending_refunds()


@shared_task(name='seller_operations.send_reorder_digests')
def send_reorder_digests():
    """CH13 — daily 08:00 low-stock reorder digest (one per seller)."""
    from . import services
    return services.send_reorder_digests()


@shared_task(name='seller_operations.sweep_sla_deadlines')
def sweep_sla_deadlines():
    """CH14 — reminders + LATE marking for fulfilment SLA."""
    from . import services
    return services.sweep_sla_deadlines()


@shared_task(name='seller_operations.escalate_stale_holds')
def escalate_stale_holds():
    """CH15 — payment-hold disputes open > 30 days escalate to Head of Finance."""
    from . import services
    return services.escalate_stale_holds()


@shared_task(name='seller_operations.rescan_compliance')
def rescan_compliance():
    """CH16 — re-scan fixed violations + auto-remove overdue HIGH severity."""
    from . import services
    return services.rescan_compliance()


@shared_task(name='seller_operations.compute_market_benchmarks')
def compute_market_benchmarks():
    """CH19 — weekly anonymised category benchmarks."""
    from . import services
    return services.compute_market_benchmarks()


@shared_task(name='seller_operations.snapshot_kpis')
def snapshot_kpis():
    """CH24 — daily KPI snapshot."""
    from . import services
    snap = services.snapshot_kpis()
    return {'date': str(snap.snapshot_date)}
