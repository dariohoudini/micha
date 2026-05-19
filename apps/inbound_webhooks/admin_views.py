"""apps/inbound_webhooks/admin_views.py — admin endpoints.

Mounted at /api/v1/admin/inbound-webhooks/. Admin-only.

  GET    /events/?provider=&event_type=&status=&reference=&limit=
  GET    /events/<id>/
  GET    /failures/?hours=
  GET    /stats/
  POST   /events/<id>/replay/
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta

from apps.users.permissions import IsAdminOrSuperuser

from . import admin_service


def _audit(request, action, *, metadata=None):
    try:
        from apps.admin_actions.models import AdminActionLog
        AdminActionLog.log(
            request, f'inbound_webhook_{action}', None,
            metadata=metadata or {},
        )
    except Exception:
        pass


class EventListView(APIView):
    """GET /api/v1/admin/inbound-webhooks/events/"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        p = request.query_params
        since = None
        if p.get('since_hours'):
            try:
                since = timezone.now() - timedelta(
                    hours=int(p['since_hours']),
                )
            except (TypeError, ValueError):
                pass
        try:
            limit = int(p.get('limit', 50))
        except (TypeError, ValueError):
            limit = 50
        rows = admin_service.list_events(
            provider=p.get('provider') or None,
            event_type=p.get('event_type') or None,
            status=p.get('status') or None,
            reference=p.get('reference') or None,
            since=since, limit=limit,
        )
        return Response({'count': len(rows), 'results': rows})


class EventDetailView(APIView):
    """GET /api/v1/admin/inbound-webhooks/events/<id>/"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, event_id):
        try:
            return Response(admin_service.get_event(event_id))
        except admin_service.WebhookAdminError as e:
            return Response({'error': 'not_found', 'detail': str(e)},
                            status=404)


class RecentFailuresView(APIView):
    """GET /api/v1/admin/inbound-webhooks/failures/?hours=1"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        try:
            hours = int(request.query_params.get('hours', 1))
        except (TypeError, ValueError):
            hours = 1
        return Response(admin_service.recent_failures(hours=hours))


class StatsView(APIView):
    """GET /api/v1/admin/inbound-webhooks/stats/"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        return Response(admin_service.stats())


class ReplayView(APIView):
    """POST /api/v1/admin/inbound-webhooks/events/<id>/replay/

    Re-runs the registered replay handler with the original parsed
    payload. The audit row's cached response is overwritten with the
    new outcome — so subsequent provider-side replays of the same
    body see the updated response, not the original failure.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, event_id):
        try:
            result = admin_service.replay_event(
                event_id, actor=request.user,
            )
        except admin_service.WebhookAdminError as e:
            return Response({'error': 'replay_error', 'detail': str(e)},
                            status=400)
        _audit(request, 'replay', metadata={
            'event_id': event_id,
            'new_status': result['status'],
            'new_response_status': result['response_status'],
        })
        return Response(result)
