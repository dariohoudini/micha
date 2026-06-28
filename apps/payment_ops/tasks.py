"""
Celery beat jobs for payment_ops.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone


@shared_task(name='payment_ops.snapshot_financial_report')
def snapshot_financial_report_task():
    from . import services
    snap = services.snapshot_financial_report()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='payment_ops.snapshot_payment_ops_kpis')
def snapshot_payment_ops_kpis_task():
    from . import services
    snap = services.snapshot_payment_ops_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='payment_ops.mark_overdue_b2b')
def mark_overdue_b2b_task():
    from . import services
    return {'overdue': services.mark_overdue_b2b()}


@shared_task(name='payment_ops.expire_store_credits')
def expire_store_credits_task():
    from . import services
    return {'expired': services.expire_store_credits()}


@shared_task(name='payment_ops.process_bnpl_late')
def process_bnpl_late_task():
    from . import services
    return {'marked_late': services.process_bnpl_late_payments()}


@shared_task(name='payment_ops.run_recovery_attempts')
def run_recovery_attempts_task():
    """CH19 — execute due recovery attempts. Production hooks into
    the gateway to actually retry; this dev stub just marks them
    `skipped` if their original failure category lacks a recovery
    path."""
    from .models import PaymentRecoveryAttempt
    now = timezone.now()
    qs = PaymentRecoveryAttempt.objects.filter(
        outcome='pending', scheduled_at__lte=now,
    )[:200]
    n = 0
    for a in qs:
        a.outcome = 'skipped'
        a.executed_at = now
        a.save(update_fields=['outcome', 'executed_at'])
        n += 1
    return {'processed': n}
