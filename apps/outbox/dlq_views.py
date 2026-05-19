"""
apps/outbox/dlq_views.py — Admin endpoints for DLQ triage.

Mounted at /api/v1/admin/outbox/. All endpoints require admin
permission via IsAdminOrSuperuser.

Endpoints:

  GET    /dead/                      list dead events
  GET    /stale-retrying/            events stuck in RETRYING > 24h
  GET    /stats/                     dead-count + oldest-age summary
  POST   /<id>/requeue/              requeue one event
  POST   /requeue-bulk/              requeue many at once (topic + since)
  POST   /<id>/discard/              permanently remove one event

Every write is audited via AdminActionLog so we know who unstuck
what during incident response.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from apps.users.permissions import IsAdminOrSuperuser

from . import dlq


class _AuditMixin:
    """Centralised AdminActionLog write so all DLQ actions trace back
    to a specific admin."""

    @staticmethod
    def _audit(request, action, *, metadata=None):
        try:
            from apps.admin_actions.models import AdminActionLog
            AdminActionLog.log(
                request, f'outbox_dlq_{action}', None,
                metadata=metadata or {},
            )
        except Exception:
            pass


class DLQDeadListView(APIView):
    """GET /api/v1/admin/outbox/dead/?topic=&limit=50&since_hours=24"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        topic = (request.query_params.get('topic') or '').strip() or None
        try:
            limit = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            limit = 50
        since = None
        if request.query_params.get('since_hours'):
            try:
                hours = int(request.query_params['since_hours'])
                since = timezone.now() - timedelta(hours=hours)
            except (TypeError, ValueError):
                pass
        return Response({
            'results': dlq.list_dead(topic=topic, limit=limit, since=since),
            'total_dead': dlq.dead_count(),
        })


class DLQStaleRetryingView(APIView):
    """GET /api/v1/admin/outbox/stale-retrying/?hours=24"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        try:
            hours = int(request.query_params.get('hours', 24))
        except (TypeError, ValueError):
            hours = 24
        older_than = timedelta(hours=max(1, hours))
        return Response({
            'results': dlq.stale_retrying(older_than=older_than),
            'total_stale': dlq.stale_retrying_count(older_than=older_than),
        })


class DLQStatsView(APIView):
    """GET /api/v1/admin/outbox/stats/ — Snapshot for the ops dashboard."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        return Response({
            'dead_count': dlq.dead_count(),
            'oldest_dead_age_seconds': dlq.oldest_dead_age_seconds(),
            'stale_retrying_count_24h': dlq.stale_retrying_count(),
            'stale_retrying_count_1h': dlq.stale_retrying_count(
                older_than=timedelta(hours=1),
            ),
        })


class DLQRequeueView(_AuditMixin, APIView):
    """POST /api/v1/admin/outbox/<id>/requeue/  body: {reset_attempts?: bool}

    Defaults: reset_attempts=True. Pass false to give the event ONE
    more try without resetting the count (useful for "is the handler
    really fixed?" checks).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, event_id):
        reset = bool(request.data.get('reset_attempts', True))
        try:
            result = dlq.requeue(
                event_id, reset_attempts=reset, actor=request.user,
            )
        except dlq.DLQError as e:
            return Response({'error': 'dlq_error', 'detail': str(e)},
                            status=400)
        self._audit(request, 'requeue', metadata={
            'event_id': str(event_id),
            'topic': result['topic'],
            'reset_attempts': reset,
        })
        return Response(result)


class DLQRequeueBulkView(_AuditMixin, APIView):
    """POST /api/v1/admin/outbox/requeue-bulk/

    body: {topic?, since_hours?, limit?, reset_attempts?}

    Requeues all DEAD events matching the filter. Caps at
    ``limit`` (default 1000) so an over-broad requeue can't flood
    the dispatcher.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        topic = (request.data.get('topic') or '').strip() or None
        since = None
        if request.data.get('since_hours'):
            try:
                hours = int(request.data['since_hours'])
                since = timezone.now() - timedelta(hours=hours)
            except (TypeError, ValueError):
                pass
        try:
            limit = int(request.data.get('limit', 1000))
        except (TypeError, ValueError):
            limit = 1000
        limit = max(1, min(limit, 5000))
        reset = bool(request.data.get('reset_attempts', True))

        result = dlq.requeue_bulk(
            topic=topic, since=since, limit=limit,
            reset_attempts=reset, actor=request.user,
        )
        self._audit(request, 'requeue_bulk', metadata={
            'topic': topic, 'since_hours': request.data.get('since_hours'),
            'requeued': result['requeued'], 'reset_attempts': reset,
        })
        return Response(result)


class DLQDiscardView(_AuditMixin, APIView):
    """POST /api/v1/admin/outbox/<id>/discard/  body: {reason?}

    Permanently removes the event. For events whose business context
    no longer applies — e.g. an order-confirmation event for an order
    that was manually refunded before this notification could fire.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, event_id):
        reason = (request.data.get('reason') or '').strip()[:200]
        try:
            result = dlq.discard(event_id, reason=reason, actor=request.user)
        except dlq.DLQError as e:
            return Response({'error': 'dlq_error', 'detail': str(e)},
                            status=400)
        self._audit(request, 'discard', metadata={
            'event_id': str(event_id),
            'topic': result.get('topic'),
            'reason': reason,
        })
        return Response(result)
