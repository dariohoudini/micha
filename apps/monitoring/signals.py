"""
Celery signals — automatically records every task execution.
"""
import logging
import time
from celery import signals
from django.utils import timezone

logger = logging.getLogger(__name__)

_task_start_times = {}


@signals.task_prerun.connect
def task_prerun_handler(task_id, task, *args, **kwargs):
    _task_start_times[task_id] = time.time()
    try:
        from apps.monitoring.models import TaskExecution
        TaskExecution.objects.update_or_create(
            task_id=task_id,
            defaults={
                'task_name': task.name,
                'status': 'started',
                'started_at': timezone.now(),
            }
        )
    except Exception as e:
        logger.debug(f'Monitoring prerun error: {e}')


@signals.task_success.connect
def task_success_handler(sender, result, **kwargs):
    task_id = sender.request.id
    if not task_id:
        return
    start = _task_start_times.pop(task_id, None)
    duration = time.time() - start if start else None
    try:
        from apps.monitoring.models import TaskExecution
        summary = {}
        if isinstance(result, dict):
            summary = {k: v for k, v in result.items() if isinstance(v, (str, int, float, bool))}
        elif isinstance(result, (int, str)):
            summary = {'result': result}
        TaskExecution.objects.filter(task_id=task_id).update(
            status='success',
            completed_at=timezone.now(),
            duration_seconds=duration,
            result_summary=summary,
        )
    except Exception as e:
        logger.debug(f'Monitoring success error: {e}')


@signals.task_failure.connect
def task_failure_handler(sender, task_id, exception, traceback, *args, **kwargs):
    start = _task_start_times.pop(task_id, None)
    duration = time.time() - start if start else None
    error = f'{type(exception).__name__}: {str(exception)}'
    logger.error(f'Task {sender.name} [{task_id}] FAILED: {error}')
    try:
        from apps.monitoring.models import TaskExecution
        TaskExecution.objects.filter(task_id=task_id).update(
            status='failure',
            completed_at=timezone.now(),
            duration_seconds=duration,
            error_message=error,
        )
    except Exception as e:
        logger.debug(f'Monitoring failure error: {e}')


@signals.task_retry.connect
def task_retry_handler(sender, request, reason, *args, **kwargs):
    task_id = request.id
    logger.warning(f'Task {sender.name} [{task_id}] RETRYING: {reason}')
    try:
        from apps.monitoring.models import TaskExecution
        obj = TaskExecution.objects.filter(task_id=task_id).first()
        if obj:
            obj.status = 'retry'
            obj.retries += 1
            obj.error_message = str(reason)
            obj.save(update_fields=['status', 'retries', 'error_message'])
    except Exception as e:
        logger.debug(f'Monitoring retry error: {e}')
