"""
apps/data_rights/views.py

User-facing endpoints for data-subject rights.

  POST /api/v1/account/data-request/     — body {kind: 'export'|'erase'}
  GET  /api/v1/account/data-request/     — list user's own requests
  GET  /api/v1/account/data-request/<id>/ — single request status

Erase is irreversible from the user's POV; we require an explicit
confirm_phrase to prevent accidental clicks.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import DataSubjectRequest, RequestKind
from . import service


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff else (request.META.get('REMOTE_ADDR') or ''))[:45]


def _ua(request) -> str:
    return (request.META.get('HTTP_USER_AGENT') or '')[:200]


def _serialize(req):
    return {
        'id': req.id,
        'kind': req.kind,
        'status': req.status,
        'created_at': req.created_at,
        'started_at': req.started_at,
        'completed_at': req.completed_at,
        'sla_deadline_at': req.sla_deadline_at,
        'payload_summary': (req.payload or {}).get('summary') if req.payload else None,
        'error': req.error or '',
    }


CONFIRM_PHRASE = 'I understand this is irreversible'


class DataRequestView(APIView):
    """POST create / GET list."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        kind = (request.data.get('kind') or '').strip()
        if kind not in {RequestKind.EXPORT, RequestKind.ERASE}:
            return Response({'error': 'validation_error',
                             'detail': 'kind must be "export" or "erase".'},
                            status=400)
        if kind == RequestKind.ERASE:
            confirm = (request.data.get('confirm_phrase') or '').strip()
            if confirm != CONFIRM_PHRASE:
                return Response({
                    'error': 'confirmation_required',
                    'detail': f'confirm_phrase must equal "{CONFIRM_PHRASE}".',
                }, status=400)

        # One in-flight request per user per kind — refuse stacking.
        already = DataSubjectRequest.objects.filter(
            user=request.user, kind=kind,
            status__in=('pending', 'running'),
        ).exists()
        if already:
            return Response({
                'error': 'already_in_flight',
                'detail': f'You already have a {kind} request in progress.',
            }, status=409)

        ip = _client_ip(request)
        ua = _ua(request)
        if kind == RequestKind.EXPORT:
            req = service.request_export(request.user, source_ip=ip, user_agent=ua)
        else:
            req = service.request_erase(request.user, source_ip=ip, user_agent=ua)
        return Response(_serialize(req), status=201)

    def get(self, request):
        rows = (
            DataSubjectRequest.objects
            .filter(user=request.user)
            .order_by('-created_at')[:50]
        )
        return Response({'results': [_serialize(r) for r in rows]})


class DataRequestDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        req = get_object_or_404(
            DataSubjectRequest, pk=pk, user=request.user,
        )
        # For EXPORT, include the manifest inline. Frontend renders or
        # offers a download button. For ERASE, just status + summary.
        body = _serialize(req)
        if req.kind == RequestKind.EXPORT and req.payload:
            body['manifest'] = req.payload.get('manifest')
        return Response(body)
