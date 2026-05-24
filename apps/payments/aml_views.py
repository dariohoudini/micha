"""
Admin endpoints for AML monitoring (R2).

  GET  /api/v1/payments/aml/alerts/[?status=open|under_review|reported|dismissed]
  GET  /api/v1/payments/aml/alerts/<pk>/
  POST /api/v1/payments/aml/alerts/<pk>/review/   {action: 'report'|'dismiss', note?}
"""
from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser
from .aml import AMLAlert


log = logging.getLogger('micha.aml')


class _AlertPagination(PageNumberPagination):
    page_size = 25
    max_page_size = 200


class AMLAlertListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]
    pagination_class = _AlertPagination

    def get(self, request):
        qs = (
            AMLAlert.objects
            .all()
            .select_related('user', 'reviewed_by', 'payment', 'payout')
        )
        status_q = request.query_params.get('status')
        if status_q:
            qs = qs.filter(status=status_q)
        else:
            qs = qs.filter(status__in=('open', 'under_review'))
        kind = request.query_params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)

        qs = qs.order_by('-created_at')
        paginator = _AlertPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            _serialize(a) for a in page
        ])


class AMLAlertDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def get(self, request, pk):
        alert = get_object_or_404(AMLAlert, pk=pk)
        return Response({
            **_serialize(alert),
            'detector_payload': alert.detector_payload,
        })


class AMLAlertReviewView(APIView):
    """``POST .../alerts/<pk>/review/`` body {action: 'report'|'dismiss', note}.

    'report'  → status=reported (officer filed STR with FIU)
    'dismiss' → status=dismissed (false positive / cleared)
    Both record reviewed_by + reviewed_at.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def post(self, request, pk):
        alert = get_object_or_404(AMLAlert, pk=pk)
        action = (request.data.get('action') or '').lower()
        note = (request.data.get('note') or '')[:2000]

        if alert.status in ('reported', 'dismissed'):
            return Response(
                {'error': 'invalid_state',
                 'detail': f'Alert is already terminal: {alert.status}'},
                status=409,
            )

        if action == 'report':
            alert.status = 'reported'
        elif action == 'dismiss':
            alert.status = 'dismissed'
        else:
            return Response(
                {'error': 'validation_error',
                 'detail': "action must be 'report' or 'dismiss'."},
                status=400,
            )

        alert.reviewed_by = request.user
        alert.review_note = note
        alert.reviewed_at = timezone.now()
        alert.save(update_fields=[
            'status', 'reviewed_by', 'review_note', 'reviewed_at',
        ])

        # Audit log
        try:
            from apps.admin_actions.models import AdminActionLog
            AdminActionLog.log(
                request=request,
                action='issue_refund',  # reusing nearest existing action
                target=alert,
                note=f'AML alert {action}: {note}',
                metadata={
                    'alert_id': alert.pk, 'kind': alert.kind,
                    'severity': alert.severity, 'new_status': alert.status,
                },
            )
        except Exception:
            log.warning('aml: audit-log failed', exc_info=True)

        return Response(_serialize(alert))


def _serialize(a: AMLAlert) -> dict:
    return {
        'id': a.pk,
        'kind': a.kind,
        'severity': a.severity,
        'status': a.status,
        'user_id': a.user_id,
        'user_email': getattr(a.user, 'email', None) if a.user else None,
        'payment_id': a.payment_id,
        'payout_id': a.payout_id,
        'aggregate_amount': str(a.aggregate_amount),
        'reason': a.reason,
        'reviewed_by_email': (
            getattr(a.reviewed_by, 'email', None) if a.reviewed_by else None
        ),
        'review_note': a.review_note,
        'created_at': a.created_at.isoformat(),
        'reviewed_at': a.reviewed_at.isoformat() if a.reviewed_at else None,
    }
