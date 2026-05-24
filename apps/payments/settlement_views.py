"""
apps/payments/settlement_views.py

Admin endpoints for settlement reconciliation:

  POST /api/v1/payments/settlement/upload/   upload a CSV, triggers a recon run
  GET  /api/v1/payments/settlement/runs/     list past runs
  GET  /api/v1/payments/settlement/runs/<pk>/  run detail (with drifts)
"""
from __future__ import annotations

from datetime import datetime

from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser
from .settlement import (
    SettlementDrift,
    SettlementReconRun,
    parse_settlement_csv,
    reconcile_settlement_rows,
)


class SettlementUploadView(APIView):
    """``POST /api/v1/payments/settlement/upload/``

    multipart/form-data with:
      file              CSV file (required)
      settlement_date   YYYY-MM-DD (required)
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def post(self, request):
        f = request.FILES.get('file')
        date_str = (request.data.get('settlement_date') or '').strip()
        if not f:
            return Response(
                {'error': 'validation_error', 'detail': 'file required.'},
                status=400,
            )
        try:
            settlement_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response(
                {'error': 'validation_error',
                 'detail': 'settlement_date must be YYYY-MM-DD.'},
                status=400,
            )

        try:
            rows = parse_settlement_csv(f.read())
        except Exception as e:
            return Response(
                {'error': 'parse_error', 'detail': str(e)[:200]},
                status=400,
            )

        run = reconcile_settlement_rows(rows, settlement_date=settlement_date)

        return Response({
            'run_id': run.pk,
            'settlement_date': run.settlement_date.isoformat(),
            'row_count': run.row_count,
            'matched': run.matched,
            'drift_rows': run.drift_rows,
            'unknown_rows': run.unknown_rows,
            'total_gross': str(run.total_gross),
            'total_fees': str(run.total_fees),
            'total_net': str(run.total_net),
            'total_drift': str(run.total_drift),
        }, status=201)


class SettlementRunPagination(PageNumberPagination):
    page_size = 25
    max_page_size = 100


class SettlementRunListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def get(self, request):
        qs = SettlementReconRun.objects.all().order_by('-settlement_date')
        paginator = SettlementRunPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            {
                'id': r.pk,
                'settlement_date': r.settlement_date.isoformat(),
                'row_count': r.row_count,
                'matched': r.matched,
                'drift_rows': r.drift_rows,
                'unknown_rows': r.unknown_rows,
                'total_drift': str(r.total_drift),
                'started_at': r.started_at.isoformat(),
                'finished_at': r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in page
        ])


class SettlementRunDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def get(self, request, pk):
        try:
            run = SettlementReconRun.objects.get(pk=pk)
        except SettlementReconRun.DoesNotExist:
            return Response({'error': 'not_found'}, status=404)
        drifts = SettlementDrift.objects.filter(run=run).order_by('-created_at')[:200]
        return Response({
            'id': run.pk,
            'settlement_date': run.settlement_date.isoformat(),
            'row_count': run.row_count,
            'matched': run.matched,
            'drift_rows': run.drift_rows,
            'unknown_rows': run.unknown_rows,
            'total_gross': str(run.total_gross),
            'total_fees': str(run.total_fees),
            'total_net': str(run.total_net),
            'total_drift': str(run.total_drift),
            'drifts': [
                {
                    'id': d.pk,
                    'kind': d.kind,
                    'gateway_reference': d.gateway_reference,
                    'type': d.type,
                    'psp_amount': str(d.psp_amount),
                    'ledger_amount': str(d.ledger_amount),
                    'drift_amount': str(d.drift_amount),
                    'resolved': d.resolved,
                    'created_at': d.created_at.isoformat(),
                }
                for d in drifts
            ],
        })
