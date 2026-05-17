"""apps/gift_cards/tasks.py — periodic expiry sweep."""
import logging
from celery import shared_task
from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='gift_cards.expire_overdue')
@singleton_task('beat:gift_cards.expire_overdue')
def expire_overdue():
    from apps.gift_cards.service import expire_overdue_cards
    return expire_overdue_cards()
