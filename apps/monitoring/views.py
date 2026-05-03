"""
Admin API for task monitoring dashboard.
"""
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from .models import TaskExecution


class TaskMonitoringView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        since = timezone.now() - timedelta(hours=24)
        tasks = TaskExecution.objects.filter(started_at__gte=since)

        # Summary stats
        stats = tasks.aggregate(
            total=Count('id'),
            success=Count('id', filter=Q(status='success')),
            failed=Count('id', filter=Q(status='failure')),
            retried=Count('id', filter=Q(status='retry')),
            avg_duration=Avg('duration_seconds', filter=Q(status='success')),
        )

        # Failing tasks
        failing = list(
            tasks.filter(status='failure')
            .values('task_name', 'error_message', 'started_at', 'task_id')
            .order_by('-started_at')[:20]
        )

        # Per-task summary
        per_task = list(
            tasks.values('task_name')
            .annotate(
                runs=Count('id'),
                successes=Count('id', filter=Q(status='success')),
                failures=Count('id', filter=Q(status='failure')),
                avg_duration=Avg('duration_seconds'),
            )
            .order_by('-runs')
        )

        # Last run per task
        last_runs = {}
        for task in TaskExecution.objects.values('task_name').distinct():
            name = task['task_name']
            last = TaskExecution.objects.filter(task_name=name).order_by('-started_at').first()
            if last:
                last_runs[name] = {
                    'status': last.status,
                    'started_at': last.started_at.isoformat(),
                    'duration': last.duration_display,
                }

        return Response({
            'period': '24h',
            'stats': stats,
            'failing_tasks': failing,
            'per_task': per_task,
            'last_runs': last_runs,
            'scheduled_count': 28,
        })


class TaskHealthView(APIView):
    """Quick health check — returns 200 if all critical tasks ran recently."""
    permission_classes = [IsAdminUser]

    CRITICAL_TASKS = [
        'apps.payments.tasks.release_held_earnings',
        'apps.inventory.tasks.clean_expired_reservations',
        'apps.users.tasks.cleanup_expired_otps',
        'apps.trust.tasks.run_fraud_sweep',
    ]
    MAX_AGE_HOURS = {
        'apps.payments.tasks.release_held_earnings': 2,
        'apps.inventory.tasks.clean_expired_reservations': 1,
        'apps.users.tasks.cleanup_expired_otps': 2,
        'apps.trust.tasks.run_fraud_sweep': 25,
    }

    def get(self, request):
        issues = []
        for task_name in self.CRITICAL_TASKS:
            max_age = self.MAX_AGE_HOURS.get(task_name, 25)
            since = timezone.now() - timedelta(hours=max_age)
            last = TaskExecution.objects.filter(
                task_name=task_name,
                status='success',
                completed_at__gte=since,
            ).order_by('-completed_at').first()
            if not last:
                issues.append({
                    'task': task_name.split('.')[-1],
                    'issue': f'No successful run in last {max_age}h',
                })

        return Response({
            'healthy': len(issues) == 0,
            'issues': issues,
            'checked_at': timezone.now().isoformat(),
        }, status=200 if not issues else 503)
