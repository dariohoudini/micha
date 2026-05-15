"""
apps/sagas/models.py

Durable record of a multi-step business operation that spans more than one
local transaction (typically because at least one step is an external network
call). The orchestrator can crash mid-saga and a recovery worker will pick up
where it left off — that's what makes a saga more than just a transaction.

Status transitions:

    pending  → running                     (runner picked it up)
    running  → completed                   (all forward steps succeeded)
    running  → compensating                (a step failed; rolling back)
    compensating → failed                  (compensations all completed cleanly)
    compensating → needs_attention         (a compensation itself failed)
    running  → waiting                     (step parked the saga to await
                                            external signal — webhook, timer)
    waiting  → running                     (external signal resumed it)
    *        → abandoned                   (deadline passed without resolution)

The runner is responsible for ensuring at most one worker advances a given
saga at a time (via SELECT FOR UPDATE on the row).
"""
from django.db import models


class SagaStatus(models.TextChoices):
    PENDING          = 'pending',          'Pending'
    RUNNING          = 'running',          'Running'
    WAITING          = 'waiting',          'Waiting (parked)'
    COMPLETED        = 'completed',        'Completed'
    COMPENSATING     = 'compensating',     'Compensating'
    FAILED           = 'failed',           'Failed (compensated cleanly)'
    NEEDS_ATTENTION  = 'needs_attention',  'Needs operator attention'
    ABANDONED        = 'abandoned',        'Abandoned (timeout)'


class Saga(models.Model):
    """A running instance of a saga definition. The definition lives in code
    (see apps/sagas/registry.py); the instance lives here so it survives
    process crashes and can be inspected by humans."""

    name = models.CharField(max_length=80, db_index=True,
                            help_text='Saga definition name, registered in code')
    # Free-form reference back to the business object this saga is about
    # (e.g. ref_type='order', ref_id=<uuid>). Used by the ops queue to
    # display "Saga X for Order Y".
    ref_type = models.CharField(max_length=40, blank=True, db_index=True)
    ref_id   = models.CharField(max_length=80, blank=True, db_index=True)

    status = models.CharField(
        max_length=20, choices=SagaStatus.choices,
        default=SagaStatus.PENDING, db_index=True,
    )

    # Shared mutable state passed between steps. Each step can read prior
    # results and write its own. Kept JSON-serialisable so the saga survives
    # restarts cleanly.
    payload = models.JSONField(default=dict)

    # Index of the next step to execute. On compensation we walk backwards
    # from (current_step - 1) down to 0.
    current_step = models.PositiveIntegerField(default=0)

    # Per-step audit trail: [{step, phase: forward|compensate, status, ts, error?}]
    steps_log = models.JSONField(default=list)

    # Top-level error message when the saga ended in failure or needs_attention.
    error = models.TextField(blank=True)

    # If status == waiting, the saga is parked until this deadline. After it
    # passes, the recovery sweeper will resume the saga (which typically
    # triggers compensation via a "timeout" exception in the next step).
    wait_until = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'wait_until']),
            models.Index(fields=['name', 'status']),
            models.Index(fields=['ref_type', 'ref_id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'Saga<{self.name}#{self.id} {self.status}>'

    def append_log(self, step, phase, status, error=''):
        from django.utils import timezone
        entry = {
            'step': step, 'phase': phase, 'status': status,
            'ts': timezone.now().isoformat(),
        }
        if error:
            entry['error'] = error[:500]
        self.steps_log.append(entry)
