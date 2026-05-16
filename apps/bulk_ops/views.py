"""
apps/bulk_ops/views.py — admin endpoints for creating, monitoring, cancelling.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import BulkJob, BulkJobItem, ItemStatus, JobStatus
from .registry import all_names, get as get_handler
from . import service


def _serialize_job(j):
    return {
        'id': j.id, 'name': j.name, 'status': j.status,
        'total': j.total, 'processed': j.processed,
        'failed': j.failed, 'skipped': j.skipped,
        'params': j.params, 'error': (j.error or '')[:500],
        'created_at': j.created_at, 'started_at': j.started_at,
        'finished_at': j.finished_at,
        'requested_by_email': j.requested_by.email if j.requested_by_id else None,
    }


class BulkJobListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = BulkJob.objects.all().order_by('-created_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        rows = qs[:50]
        return Response({
            'kinds': all_names(),
            'results': [_serialize_job(j) for j in rows],
        })

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'validation_error',
                             'detail': 'name required'}, status=400)
        try:
            get_handler(name)
        except KeyError:
            return Response({'error': 'unknown_kind',
                             'detail': f'kinds: {all_names()}'}, status=400)
        item_refs = request.data.get('item_refs') or []
        if not isinstance(item_refs, list) or not item_refs:
            return Response({'error': 'validation_error',
                             'detail': 'item_refs must be a non-empty list'},
                            status=400)
        if len(item_refs) > 10000:
            return Response({'error': 'too_many',
                             'detail': 'max 10k items per job'}, status=400)

        try:
            job = service.create_job(
                name=name, item_refs=item_refs,
                params=request.data.get('params') or {},
                requested_by=request.user,
            )
        except ValueError as e:
            return Response({'error': 'validation_error',
                             'detail': str(e)}, status=400)

        # Kick off processing — drive_job is the worker; on Celery-less
        # environments (tests) the beat sweeper will catch it.
        try:
            from .tasks import drive_job
            drive_job.delay(job.id)
        except Exception:
            pass

        return Response(_serialize_job(job), status=201)


class BulkJobDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        job = get_object_or_404(BulkJob, pk=pk)
        # Include a sample of items, prioritising errors so the admin can
        # triage what went wrong without scrolling the happy-path rows.
        errors = list(
            BulkJobItem.objects.filter(job=job, status=ItemStatus.ERROR)
            .order_by('processed_at')[:50]
            .values('item_ref', 'status', 'error', 'processed_at')
        )
        others = list(
            BulkJobItem.objects.filter(job=job).exclude(status=ItemStatus.ERROR)
            .order_by('-processed_at')[:50]
            .values('item_ref', 'status', 'result', 'processed_at')
        )
        return Response({
            **_serialize_job(job),
            'items': {'errors': errors, 'recent': others},
        })


class BulkJobCancelView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        job = service.cancel_job(pk, user=request.user)
        if job is None:
            return Response({'error': 'not_found'}, status=404)
        return Response(_serialize_job(job))
