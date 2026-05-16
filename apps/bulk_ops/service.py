"""
apps/bulk_ops/service.py

Public entrypoints:

  create_job(name, item_refs, params, requested_by)
    Insert the BulkJob + one BulkJobItem per ref. Returns the job.

  process_job(job_id, batch_size=50)
    Pull up-to-batch_size pending items, run the handler for each, record
    outcomes. Idempotent — safe to call multiple times; the singleton lock
    + select_for_update inside ensures items aren't double-processed.

  cancel_job(job_id, user)
    Mark the job cancelled. Any items in `pending` are short-circuited as
    `skipped`; items already `processing` complete naturally (we don't kill
    them mid-flight — they'd leave state inconsistent).
"""
from __future__ import annotations
import logging
import traceback

from django.db import transaction
from django.utils import timezone

from .models import BulkJob, BulkJobItem, JobStatus, ItemStatus
from .registry import get as get_handler

log = logging.getLogger(__name__)


def create_job(*, name: str, item_refs: list, params: dict | None = None,
               requested_by=None) -> BulkJob:
    """Insert the job and one item per ref. De-dupes refs to avoid double-
    processing if the caller accidentally includes the same id twice."""
    get_handler(name)  # raises early if the kind is unknown

    refs = list(dict.fromkeys(str(r) for r in (item_refs or []) if r is not None))
    if not refs:
        raise ValueError('item_refs must be non-empty')

    with transaction.atomic():
        job = BulkJob.objects.create(
            name=name, params=params or {},
            requested_by=requested_by if (requested_by and getattr(requested_by, 'is_authenticated', False)) else None,
            total=len(refs),
        )
        BulkJobItem.objects.bulk_create([
            BulkJobItem(job=job, item_ref=r) for r in refs
        ])
    return job


def process_job(job_id: int, *, batch_size: int = 50) -> dict:
    """Process up to ``batch_size`` pending items for the job. Designed to
    be called repeatedly by a Celery task until the job reaches a terminal
    state — keeps each invocation bounded so we don't block a worker for
    minutes on a 50k-item job."""
    job = BulkJob.objects.filter(pk=job_id).first()
    if job is None:
        return {'error': 'not_found'}
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return {'status': job.status, 'done': True}

    if job.status == JobStatus.PENDING:
        BulkJob.objects.filter(pk=job.pk).update(
            status=JobStatus.RUNNING, started_at=timezone.now(),
        )
        job.refresh_from_db()

    handler = get_handler(job.name)

    # Take a batch of pending items, lock them so other workers can't grab
    # the same ones. select_for_update(skip_locked=True) so concurrent
    # process_job calls can run in parallel without contention.
    with transaction.atomic():
        items = list(
            BulkJobItem.objects
            .select_for_update(skip_locked=True)
            .filter(job=job, status=ItemStatus.PENDING)
            .order_by('id')[:batch_size]
        )
        if not items:
            return _maybe_finalise(job)

        BulkJobItem.objects.filter(pk__in=[i.pk for i in items]).update(
            status=ItemStatus.PROCESSING,
        )

    # Process each item outside the lock window — handlers may be slow
    # (network calls etc.) and we don't want to hold a row lock for that.
    done = 0
    errors = 0
    skipped = 0
    for it in items:
        try:
            result = handler.fn(it.item_ref, job.params or {}, job.requested_by)
            if isinstance(result, dict) and result.get('skipped'):
                BulkJobItem.objects.filter(pk=it.pk).update(
                    status=ItemStatus.SKIPPED, result=result,
                    processed_at=timezone.now(),
                )
                skipped += 1
            else:
                BulkJobItem.objects.filter(pk=it.pk).update(
                    status=ItemStatus.DONE,
                    result=result if isinstance(result, dict) else {'ok': True},
                    processed_at=timezone.now(),
                )
                done += 1
                # Optional admin audit composability — one log row per item
                if handler.audit_action and job.requested_by is not None:
                    _audit_item(handler.audit_action, it.item_ref, job)
        except Exception as e:
            BulkJobItem.objects.filter(pk=it.pk).update(
                status=ItemStatus.ERROR,
                error=f'{type(e).__name__}: {e}\n{traceback.format_exc()}'[:5000],
                processed_at=timezone.now(),
            )
            errors += 1

    # Bump aggregate counters in one update
    BulkJob.objects.filter(pk=job.pk).update(
        processed=models_F('processed') + done,
        failed=models_F('failed') + errors,
        skipped=models_F('skipped') + skipped,
    )

    return _maybe_finalise(job)


def _maybe_finalise(job: BulkJob) -> dict:
    """If no more pending items exist, flip the job into its terminal state."""
    remaining = BulkJobItem.objects.filter(
        job=job, status__in=(ItemStatus.PENDING, ItemStatus.PROCESSING),
    ).count()
    if remaining > 0:
        return {'status': job.status, 'done': False, 'remaining': remaining}

    job.refresh_from_db()
    # FAILED only if every item errored; otherwise COMPLETED (mixed outcomes
    # are normal — admins triage the .error items via the items list).
    if job.failed > 0 and job.processed == 0 and job.skipped == 0:
        terminal = JobStatus.FAILED
    else:
        terminal = JobStatus.COMPLETED
    BulkJob.objects.filter(pk=job.pk, status=JobStatus.RUNNING).update(
        status=terminal, finished_at=timezone.now(),
    )
    return {'status': terminal, 'done': True,
            'processed': job.processed, 'failed': job.failed,
            'skipped': job.skipped, 'total': job.total}


def cancel_job(job_id: int, user=None) -> BulkJob | None:
    """Soft-cancel: pending items get short-circuited to skipped; items
    already processing finish naturally (don't risk inconsistent state by
    killing mid-handler)."""
    with transaction.atomic():
        job = BulkJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None:
            return None
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return job
        # Skip remaining pending items
        skipped = BulkJobItem.objects.filter(
            job=job, status=ItemStatus.PENDING,
        ).update(status=ItemStatus.SKIPPED, processed_at=timezone.now(),
                 result={'cancelled': True})
        BulkJob.objects.filter(pk=job.pk).update(
            status=JobStatus.CANCELLED,
            skipped=models_F('skipped') + skipped,
            finished_at=timezone.now(),
            error=f'cancelled by {getattr(user, "email", "system")}'[:200],
        )
        job.refresh_from_db()
    return job


def _audit_item(action: str, item_ref: str, job: BulkJob):
    """Per-item audit row, attributed to the requesting admin."""
    try:
        from apps.admin_actions.models import AdminActionLog

        class _T:
            def __init__(self, pk): self.pk = pk
            def __str__(self): return str(self.pk)

        class _Req:
            user = job.requested_by
            META = {}

        AdminActionLog.objects.create(
            admin=job.requested_by, action=action,
            target_type='bulk_item', target_id=str(item_ref),
            target_repr=str(item_ref),
            note=f'bulk job #{job.id}',
            metadata={'bulk_job_id': job.id, 'kind': job.name},
        )
    except Exception:
        # Audit failures must not break the bulk worker.
        log.debug('per-item audit log failed for %s', item_ref)


# Imported late to avoid circular: Django F-expression
from django.db.models import F as models_F  # noqa: E402
