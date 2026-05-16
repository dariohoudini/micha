"""
apps/sagas/tasks.py

Celery tasks for the saga subsystem:

  - advance_waiting_sagas   — wake parked sagas whose wait_until has passed
  - abandon_overdue_sagas   — compensate sagas that exceeded max_lifetime
  - reap_abandoned_checkouts — domain task: spawn one saga per stuck order
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Saga, SagaStatus
from .registry import get as get_def, all_names
from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='sagas.advance_waiting')
@singleton_task('beat:sagas.advance_waiting')
def advance_waiting_sagas():
    """Wake any saga whose wait_until has elapsed."""
    from .runner import resume
    now = timezone.now()
    ids = list(
        Saga.objects
        .filter(status=SagaStatus.WAITING, wait_until__lte=now)
        .values_list('id', flat=True)[:200]
    )
    for sid in ids:
        try:
            resume(sid)
        except Exception:
            log.exception('resume saga %s failed', sid)
    return len(ids)


@shared_task(name='sagas.abandon_overdue')
@singleton_task('beat:sagas.abandon_overdue')
def abandon_overdue_sagas():
    """Force terminal state on sagas that exceeded their per-definition
    max_lifetime_seconds. Compensates any completed forward steps."""
    from .runner import abandon
    now = timezone.now()
    abandoned = 0
    # Iterate over registered defs that *have* a max lifetime
    for name in all_names():
        try:
            d = get_def(name)
        except Exception:
            continue
        if not d.max_lifetime_seconds:
            continue
        cutoff = now - timedelta(seconds=d.max_lifetime_seconds)
        ids = list(
            Saga.objects
            .filter(name=name, created_at__lt=cutoff,
                    status__in=(SagaStatus.PENDING, SagaStatus.RUNNING,
                                SagaStatus.WAITING))
            .values_list('id', flat=True)[:200]
        )
        for sid in ids:
            try:
                abandon(sid, reason='max_lifetime_exceeded')
                abandoned += 1
            except Exception:
                log.exception('abandon saga %s failed', sid)
    return abandoned


@shared_task(name='sagas.reap_abandoned_checkouts')
@singleton_task('beat:sagas.reap_abandoned_checkouts')
def reap_abandoned_checkouts(grace_minutes: int = 30):
    """Spawn an ``abandoned_checkout`` saga per order that's been sitting
    unpaid past the grace window. Idempotent — already-reaped orders won't
    create a new saga (one is enough; the saga itself is dedupe-keyed on
    order_id via outbox).
    """
    from apps.orders.models import Order
    from .runner import start, run

    cutoff = timezone.now() - timedelta(minutes=grace_minutes)
    candidates = Order.objects.filter(
        payment_status='pending', status='pending', created_at__lt=cutoff,
    ).values_list('id', flat=True)[:200]

    spawned = 0
    for oid in candidates:
        order_id = str(oid)
        # Skip if there's already a non-terminal saga for this order
        existing = Saga.objects.filter(
            name='abandoned_checkout', ref_type='order', ref_id=order_id,
        ).exclude(status__in=(
            SagaStatus.COMPLETED, SagaStatus.FAILED,
            SagaStatus.ABANDONED, SagaStatus.NEEDS_ATTENTION,
        )).exists()
        if existing:
            continue
        s = start('abandoned_checkout', ref_type='order', ref_id=order_id,
                  payload={'order_id': order_id})
        try:
            run(s.id)
            spawned += 1
        except Exception:
            log.exception('reap saga %s for order %s failed', s.id, order_id)
    return spawned
