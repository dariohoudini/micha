"""
apps/affiliates/tasks.py — periodic conversion confirmation + payout.
"""
import logging
from celery import shared_task
from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='affiliates.confirm_pending')
@singleton_task('beat:affiliates.confirm_pending')
def confirm_pending():
    from apps.affiliates.service import confirm_pending_conversions
    return confirm_pending_conversions()


@shared_task(name='affiliates.process_payouts')
@singleton_task('beat:affiliates.process_payouts')
def process_payouts():
    from apps.affiliates.service import process_payouts
    return process_payouts()
