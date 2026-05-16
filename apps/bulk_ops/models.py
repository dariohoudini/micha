"""
apps/bulk_ops/models.py

Bulk admin operations. Two tables:

  BulkJob       — the job itself. Tracks counts, status, requester, params.
  BulkJobItem   — per-row record. One row per item the job will touch,
                  so admins can see exactly which items failed.

Lifecycle:
  pending → running → completed | failed | cancelled

Items follow:
  pending → processing → done | error

Why per-item rows (not just a counter):
  When a bulk-suspend of 5000 users completes, the admin wants to know
  WHICH 12 of them failed and WHY. A counter can't answer that. Per-item
  rows also let us:
    - Resume a failed job by re-processing only items still in pending/error
    - Display real progress in the UI (97 / 5000 done, 3 errors)
    - Bound batch size by querying for next-N pending items
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class JobStatus(models.TextChoices):
    PENDING    = 'pending',    'Pending'
    RUNNING    = 'running',    'Running'
    COMPLETED  = 'completed',  'Completed'
    FAILED     = 'failed',     'Failed (all items errored)'
    CANCELLED  = 'cancelled',  'Cancelled by operator'


class ItemStatus(models.TextChoices):
    PENDING    = 'pending',    'Pending'
    PROCESSING = 'processing', 'Processing'
    DONE       = 'done',       'Done'
    ERROR      = 'error',      'Error'
    SKIPPED    = 'skipped',    'Skipped (handler opted out)'


class BulkJob(models.Model):
    """One row per bulk operation. Surfaces in the ops queue + admin UI."""
    # Name of the registered handler kind, e.g. 'users.bulk_suspend'.
    name = models.CharField(max_length=80, db_index=True)
    status = models.CharField(
        max_length=12, choices=JobStatus.choices,
        default=JobStatus.PENDING, db_index=True,
    )

    # Counts maintained as items move through states. The worker is the
    # only writer; readers see eventually-consistent counts.
    total      = models.PositiveIntegerField(default=0)
    processed  = models.PositiveIntegerField(default=0)
    failed     = models.PositiveIntegerField(default=0)
    skipped    = models.PositiveIntegerField(default=0)

    # Free-form parameters passed to each item handler (e.g. {'note': 'fraud ring March'}).
    params = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bulk_jobs_requested',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.name}#{self.id} ({self.status}: {self.processed}/{self.total})'


class BulkJobItem(models.Model):
    """One row per item the job will touch. The job's worker pulls items
    in batches, marks them processing, runs the handler, records the
    outcome. Failures are isolated to the item, not the whole job."""
    job = models.ForeignKey(
        BulkJob, on_delete=models.CASCADE, related_name='items',
    )
    # The reference into the target model — stringified PK is universal.
    item_ref = models.CharField(max_length=80, db_index=True)
    status = models.CharField(
        max_length=12, choices=ItemStatus.choices,
        default=ItemStatus.PENDING, db_index=True,
    )
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['job', 'item_ref'],
                                    name='uniq_job_item_ref'),
        ]
        indexes = [
            models.Index(fields=['job', 'status']),
        ]
