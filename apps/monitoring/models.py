"""
Task execution monitoring — tracks every beat task run.
"""
from django.db import models


class TaskExecution(models.Model):
    STATUS = [
        ('started', 'Started'),
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('retry', 'Retry'),
    ]

    task_name = models.CharField(max_length=200, db_index=True)
    task_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retries = models.IntegerField(default=0)
    result_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['task_name', '-started_at']),
            models.Index(fields=['status', '-started_at']),
        ]

    def __str__(self):
        return f'{self.task_name} [{self.status}] @ {self.started_at:%Y-%m-%d %H:%M}'

    @property
    def duration_display(self):
        if not self.duration_seconds:
            return 'N/A'
        if self.duration_seconds < 60:
            return f'{self.duration_seconds:.1f}s'
        return f'{self.duration_seconds/60:.1f}m'
