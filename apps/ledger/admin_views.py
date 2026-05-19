"""apps/ledger/admin_views.py — admin endpoints for ledger health.

Mounted at /api/v1/admin/ledger/. Admin-only via IsAdminOrSuperuser.

  GET    /health/              global invariant + unbalanced journals
  GET    /unbalanced/?limit=   list unbalanced journals for triage
  GET    /drift/?user=<id>     show cached-vs-ledger drift for one user
  GET    /drift-scan/          bulk drift scan (read-only)
  POST   /drift/<user_id>/fix/ reset cached counters to match ledger
                                (after operator has confirmed ledger is right)

Every write is audited to AdminActionLog.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from apps.users.permissions import IsAdminOrSuperuser

from . import reconciliation


User = get_user_model()


def _audit(request, action, target_user, *, metadata=None):
    try:
        from apps.admin_actions.models import AdminActionLog
        AdminActionLog.log(
            request, f'ledger_{action}', target_user,
            metadata=metadata or {},
        )
    except Exception:
        pass


class LedgerHealthView(APIView):
    """GET /api/v1/admin/ledger/health/  — full ledger health snapshot."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        global_result = reconciliation.check_global_invariant()
        unbalanced = reconciliation.find_unbalanced_journals(limit=10)
        return Response({
            'global': {
                'debit_total_cents': global_result.debit_total_cents,
                'credit_total_cents': global_result.credit_total_cents,
                'imbalance_cents': global_result.imbalance_cents,
                'is_balanced': global_result.is_balanced,
            },
            'unbalanced_journals': [
                {
                    'journal_id': j.journal_id,
                    'idempotency_key': j.idempotency_key,
                    'debit_total_cents': j.debit_total_cents,
                    'credit_total_cents': j.credit_total_cents,
                    'imbalance_cents': j.imbalance_cents,
                    'ref_type': j.ref_type,
                    'ref_id': j.ref_id,
                    'created_at': j.created_at,
                }
                for j in unbalanced
            ],
        })


class LedgerUnbalancedJournalsView(APIView):
    """GET /api/v1/admin/ledger/unbalanced/?limit=100"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 100))
        except (TypeError, ValueError):
            limit = 100
        rows = reconciliation.find_unbalanced_journals(limit=limit)
        return Response({
            'count': len(rows),
            'results': [
                {
                    'journal_id': j.journal_id,
                    'idempotency_key': j.idempotency_key,
                    'imbalance_cents': j.imbalance_cents,
                    'ref_type': j.ref_type, 'ref_id': j.ref_id,
                    'created_at': j.created_at,
                }
                for j in rows
            ],
        })


class LedgerDriftView(APIView):
    """GET /api/v1/admin/ledger/drift/?user=<id>  — show drift for one user."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        try:
            user_id = int(request.query_params.get('user', '0'))
        except (TypeError, ValueError):
            return Response({'error': 'validation_error',
                             'detail': 'user query param required'},
                            status=400)
        if not user_id:
            return Response({'error': 'validation_error',
                             'detail': 'user query param required'},
                            status=400)
        user = get_object_or_404(User, pk=user_id)
        drifts = reconciliation.reconcile_user(user)
        return Response({
            'user_id': user.pk,
            'email': user.email,
            'drift_count': len(drifts),
            'drifts': [
                {
                    'field': d.field,
                    'cached': str(d.cached_value),
                    'ledger': str(d.ledger_balance),
                    'drift': str(d.drift),
                }
                for d in drifts
            ],
        })


class LedgerDriftScanView(APIView):
    """GET /api/v1/admin/ledger/drift-scan/  — bulk read-only scan."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        result = reconciliation.scan_user_drift(
            batch_size=500, max_users=10_000,
        )
        return Response(result)


class LedgerDriftFixView(APIView):
    """POST /api/v1/admin/ledger/drift/<user_id>/fix/

    Resets the user's cached counters to match the ledger truth. Use
    AFTER inspecting via /drift/ and confirming the LEDGER is correct
    (the usual case — if the ledger is wrong, write a correction
    journal instead via a more deliberate procedure).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        fixed = reconciliation.reset_cached_counter_to_ledger(user)
        _audit(request, 'drift_fix', user, metadata={
            'fixed': fixed,
        })
        return Response({
            'user_id': user.pk,
            'email': user.email,
            'fixed': fixed,
            'detail': 'Cached counters reset to ledger truth.'
                      if fixed
                      else 'No drift detected; nothing changed.',
        })
