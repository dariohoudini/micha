"""
apps/alerts/tasks.py — periodic saved-search runner.
"""
import logging
from celery import shared_task

from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='alerts.run_saved_searches')
@singleton_task('beat:alerts.run_saved_searches')
def run_saved_searches_task(batch_size: int = 100):
    from apps.alerts.service import run_all_saved_searches
    return run_all_saved_searches(batch_size=batch_size)
