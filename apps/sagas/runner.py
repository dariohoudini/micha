"""
apps/sagas/runner.py

The saga executor. Picks a saga, locks the row, advances steps, handles
compensation. Designed so it can be invoked synchronously (during a write
request — the cheap path) AND from a recovery worker (after restarts /
wake-ups). Locking via ``select_for_update(skip_locked=True)`` prevents two
workers from advancing the same saga concurrently.
"""
import logging
import traceback

from django.db import transaction
from django.utils import timezone

from .models import Saga, SagaStatus
from .registry import get as get_def, SagaWait, SagaAbort

logger = logging.getLogger('sagas')


def start(name: str, *, ref_type: str = '', ref_id: str = '',
          payload: dict | None = None) -> Saga:
    """Create a new saga instance in PENDING state. Caller should follow up
    with ``run(saga.id)`` (or schedule that via Celery)."""
    s = Saga.objects.create(
        name=name, ref_type=ref_type, ref_id=str(ref_id) if ref_id else '',
        payload=payload or {},
    )
    logger.info(f'saga started: {s}')
    return s


def run(saga_id) -> Saga | None:
    """Advance a saga as far as it will go in one invocation. Returns the
    updated row (or None if it was locked by another worker)."""
    with transaction.atomic():
        s = (
            Saga.objects
            .select_for_update(skip_locked=True)
            .filter(pk=saga_id)
            .first()
        )
        if s is None:
            return None
        if s.status in (
            SagaStatus.COMPLETED, SagaStatus.FAILED,
            SagaStatus.ABANDONED, SagaStatus.NEEDS_ATTENTION,
        ):
            return s  # nothing to do for terminal states

        saga_def = get_def(s.name)

        if s.status == SagaStatus.COMPENSATING:
            _compensate(s, saga_def)
        else:
            _advance_forward(s, saga_def)

        s.save()
        return s


def _advance_forward(s: Saga, saga_def):
    """Run forward steps from current_step onwards until one parks or fails."""
    s.status = SagaStatus.RUNNING
    s.wait_until = None
    while s.current_step < len(saga_def.steps):
        step = saga_def.steps[s.current_step]
        try:
            step.action(s.payload, s)
        except SagaWait as w:
            s.status = SagaStatus.WAITING
            s.wait_until = w.until
            s.append_log(step.name, 'forward', 'waiting', error=w.reason)
            return
        except SagaAbort as a:
            s.append_log(step.name, 'forward', 'aborted', error=str(a))
            s.status = SagaStatus.COMPENSATING
            s.error = f'aborted at {step.name}: {a}'
            # Don't increment current_step — compensation walks from
            # current_step-1 backwards (i.e. compensates everything that
            # completed *before* this aborted step).
            _compensate(s, saga_def)
            return
        except Exception as e:
            s.append_log(step.name, 'forward', 'failed',
                         error=f'{type(e).__name__}: {e}\n{traceback.format_exc()}')
            s.error = f'{type(e).__name__}: {e}'[:500]
            s.status = SagaStatus.COMPENSATING
            _compensate(s, saga_def)
            return

        s.append_log(step.name, 'forward', 'ok')
        s.current_step += 1

    # All steps succeeded
    s.status = SagaStatus.COMPLETED
    s.completed_at = timezone.now()


def _compensate(s: Saga, saga_def):
    """Walk completed steps in reverse, running each step's compensate fn.

    If a compensation itself fails, we stop and flip to NEEDS_ATTENTION —
    operator must look. We never silently swallow compensation failures
    because the user's money / inventory may now be in an inconsistent state.
    """
    # current_step points at the step that *failed* (forward) or that would
    # be run next. We want to compensate steps 0 .. current_step-1.
    while s.current_step > 0:
        idx = s.current_step - 1
        step = saga_def.steps[idx]
        if step.compensate is None:
            s.append_log(step.name, 'compensate', 'skipped')
            s.current_step = idx
            continue
        try:
            step.compensate(s.payload, s)
            s.append_log(step.name, 'compensate', 'ok')
            s.current_step = idx
        except Exception as e:
            s.append_log(step.name, 'compensate', 'failed',
                         error=f'{type(e).__name__}: {e}\n{traceback.format_exc()}')
            s.status = SagaStatus.NEEDS_ATTENTION
            s.error = (s.error + ' | ' if s.error else '') + \
                      f'compensate({step.name}): {e}'
            s.error = s.error[:500]
            return

    s.status = SagaStatus.FAILED
    s.completed_at = timezone.now()


def resume(saga_id) -> Saga | None:
    """External signal handler: a saga in WAITING state is being told its
    wait condition has resolved. Flip to RUNNING and advance."""
    with transaction.atomic():
        s = (
            Saga.objects
            .select_for_update(skip_locked=True)
            .filter(pk=saga_id, status=SagaStatus.WAITING)
            .first()
        )
        if s is None:
            return None
        s.status = SagaStatus.RUNNING
        s.wait_until = None
        s.save(update_fields=['status', 'wait_until', 'updated_at'])
    # Run outside the lock so the runner can re-lock cleanly.
    return run(saga_id)


def abandon(saga_id, *, reason: str = 'timeout') -> Saga | None:
    """A saga's deadline passed without resolution. Move it through
    compensation if it had completed steps; otherwise just mark ABANDONED.
    Used by the recovery sweeper."""
    with transaction.atomic():
        s = (
            Saga.objects
            .select_for_update(skip_locked=True)
            .filter(pk=saga_id)
            .first()
        )
        if s is None or s.status in (
            SagaStatus.COMPLETED, SagaStatus.FAILED,
            SagaStatus.ABANDONED, SagaStatus.NEEDS_ATTENTION,
        ):
            return s
        saga_def = get_def(s.name)
        s.error = f'abandoned: {reason}'
        if s.current_step > 0:
            s.status = SagaStatus.COMPENSATING
            _compensate(s, saga_def)
        else:
            s.status = SagaStatus.ABANDONED
            s.completed_at = timezone.now()
        s.save()
        return s
