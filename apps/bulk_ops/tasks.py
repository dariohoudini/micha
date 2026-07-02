"""
apps/bulk_ops/tasks.py — Celery driver for bulk jobs.
"""
import logging

from celery import shared_task

from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='bulk_ops.drive_job', bind=True, max_retries=0,
             soft_time_limit=1500, time_limit=1800)  # bulk import: 25/30 min
def drive_job(self, job_id: int, *, max_iterations: int = 200):
    """Process a single job to completion. We loop locally (rather than
    re-queueing) up to ``max_iterations`` batches — keeps total wall time
    bounded while avoiding queue churn."""
    from .service import process_job

    # singleton_task per-job so two workers don't drive the same job.
    @singleton_task(f'bulk_ops:drive_job:{job_id}')
    def _drive():
        for _ in range(max_iterations):
            res = process_job(job_id, batch_size=50)
            if res.get('done'):
                return res
        return {'done': False, 'reason': 'max_iterations_reached'}

    return _drive()


@shared_task(name='bulk_ops.drive_pending')
@singleton_task('beat:bulk_ops.drive_pending')
def drive_pending_jobs():
    """Pick up any RUNNING/PENDING job and advance it. Belt-and-braces in
    case the create-time .delay() didn't fire (e.g. Celery restart)."""
    from .models import BulkJob, JobStatus

    ids = list(
        BulkJob.objects
        .filter(status__in=(JobStatus.PENDING, JobStatus.RUNNING))
        .values_list('id', flat=True)[:50]
    )
    for jid in ids:
        try:
            drive_job.delay(jid)
        except Exception:
            log.exception('failed to enqueue drive_job for %s', jid)
    return len(ids)
