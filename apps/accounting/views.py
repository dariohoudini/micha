"""Accounting — finance/admin REST endpoints under /api/v1/accounting/.

All endpoints are finance/admin-only (is_staff). No buyer/seller access:
the GL is internal financial truth.
"""
from datetime import date

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AccountingPeriod, FinancialStatementSnapshot, GLAccount, JournalEntry,
    ManualEntryApproval, SubLedgerReconciliation,
)


class IsFinanceAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


class ChartOfAccountsView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        return Response({'accounts': [
            {'code': a.code, 'name': a.name, 'type': a.account_type,
             'normal_balance': a.normal_balance,
             'balance_cents': services.account_balance(a.code)}
            for a in GLAccount.objects.all()]})


class TrialBalanceView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        as_of = request.query_params.get('as_of')
        as_of = date.fromisoformat(as_of) if as_of else None
        return Response(services.trial_balance(as_of=as_of))


class ProfitAndLossView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        period = request.query_params.get('period') or date.today().strftime(
            '%Y-%m')
        return Response(services.profit_and_loss(period))


class BalanceSheetView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        as_of = request.query_params.get('as_of')
        as_of = date.fromisoformat(as_of) if as_of else None
        return Response(services.balance_sheet(as_of=as_of))


class JournalListView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        qs = JournalEntry.objects.all()
        if request.query_params.get('period'):
            qs = qs.filter(period=request.query_params['period'])
        if request.query_params.get('source_id'):
            qs = qs.filter(source_id=request.query_params['source_id'])
        return Response({'entries': [
            {'id': str(e.id), 'date': e.entry_date, 'period': e.period,
             'description': e.description, 'source_type': e.source_type,
             'source_id': e.source_id, 'total_cents': e.total_cents,
             'is_reversal': e.is_reversal,
             'lines': [{'account': ln.account_id, 'debit': ln.debit_cents,
                        'credit': ln.credit_cents, 'desc': ln.description}
                       for ln in e.lines.all()]}
            for e in qs[:100]]})


class ReconciliationView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        return Response({'reconciliations': [
            {'date': r.recon_date, 'ledger': r.ledger,
             'gl_account': r.gl_account_code,
             'sub_ledger_cents': r.sub_ledger_total_cents,
             'gl_cents': r.gl_balance_cents,
             'difference_cents': r.difference_cents, 'balanced': r.balanced}
            for r in SubLedgerReconciliation.objects.order_by(
                '-recon_date')[:50]]})

    def post(self, request):
        recons = services.reconcile_sub_ledgers()
        return Response({'reconciliations': [
            {'ledger': r.ledger, 'balanced': r.balanced,
             'difference_cents': r.difference_cents} for r in recons]},
            status=status.HTTP_201_CREATED)


class ManualEntryView(APIView):
    """CH21 segregation of duties: request → a different admin approves →
    posts the journal.
    """
    permission_classes = [IsFinanceAdmin]

    def post(self, request):
        lines = request.data.get('lines') or []
        td = sum(int(line.get('debit_cents', 0)) for line in lines)
        tc = sum(int(line.get('credit_cents', 0)) for line in lines)
        if td != tc or td == 0:
            return Response({'error': 'lines must balance (debits==credits)'},
                            status=status.HTTP_400_BAD_REQUEST)
        me = ManualEntryApproval.objects.create(
            description=request.data.get('description', '')[:300],
            period=request.data.get('period') or date.today().strftime('%Y-%m'),
            entry_date=date.fromisoformat(
                request.data.get('entry_date', date.today().isoformat())),
            lines=lines, requested_by=request.user)
        return Response({'id': me.id, 'status': me.status},
                        status=status.HTTP_201_CREATED)


class ManualEntryApproveView(APIView):
    permission_classes = [IsFinanceAdmin]

    def post(self, request, entry_id):
        me = ManualEntryApproval.objects.filter(id=entry_id).first()
        if not me:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        if me.status != 'pending':
            return Response({'error': f'already {me.status}'},
                            status=status.HTTP_400_BAD_REQUEST)
        if me.requested_by_id == request.user.id:
            return Response({'error': 'approver must differ from requester'},
                            status=status.HTTP_400_BAD_REQUEST)
        decision = request.data.get('decision', 'approve')
        from django.utils import timezone
        if decision != 'approve':
            me.status = 'rejected'
            me.approved_by = request.user
            me.decided_at = timezone.now()
            me.save()
            return Response({'status': 'rejected'})
        try:
            entry = services.post_journal(
                entry_date=me.entry_date, description=me.description,
                lines=[{'account': line['account_code'],
                        'debit': line.get('debit_cents', 0),
                        'credit': line.get('credit_cents', 0),
                        'description': line.get('description', '')}
                       for line in me.lines],
                source_type='manual', posted_by=me.requested_by,
                approved_by=request.user, is_auto=False)
        except (services.UnbalancedJournal, services.PeriodLocked) as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        me.status = 'posted'
        me.approved_by = request.user
        me.posted_entry = entry
        me.decided_at = timezone.now()
        me.save()
        return Response({'status': 'posted', 'journal_entry_id': str(entry.id)})


class PeriodLockView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        return Response({'periods': [
            {'period': p.period, 'locked': p.is_locked, 'locked_at': p.locked_at}
            for p in AccountingPeriod.objects.all()[:36]]})

    def post(self, request):
        period = request.data.get('period')
        if not period:
            return Response({'error': 'period required'},
                            status=status.HTTP_400_BAD_REQUEST)
        if request.data.get('unlock'):
            services.unlock_period(period, by=request.user,
                                   reason=request.data.get('reason', ''))
            return Response({'period': period, 'locked': False})
        services.lock_period(period, locked_by=request.user)
        return Response({'period': period, 'locked': True})


class MonthEndCloseView(APIView):
    permission_classes = [IsFinanceAdmin]

    def post(self, request):
        period = request.data.get('period') or date.today().strftime('%Y-%m')
        result = services.month_end_close(
            period, by=request.user, lock=bool(request.data.get('lock', True)))
        return Response(result, status=status.HTTP_201_CREATED)


class StatementSnapshotView(APIView):
    permission_classes = [IsFinanceAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'period': s.period,
             'revenue_cents': s.total_revenue_cents,
             'gross_profit_cents': s.gross_profit_cents,
             'net_profit_cents': s.net_profit_cents,
             'assets_cents': s.total_assets_cents,
             'liabilities_cents': s.total_liabilities_cents,
             'equity_cents': s.total_equity_cents,
             'balance_sheet_balanced': s.balance_sheet_balanced,
             'trial_balance_balanced': s.trial_balance_balanced,
             'take_rate_pct': str(s.take_rate_pct),
             'gross_margin_pct': str(s.gross_margin_pct)}
            for s in FinancialStatementSnapshot.objects.order_by('-period')[:24]]})

    def post(self, request):
        period = request.data.get('period') or date.today().strftime('%Y-%m')
        snap = services.snapshot_financials(period)
        return Response({'period': snap.period,
                         'net_profit_cents': snap.net_profit_cents},
                        status=status.HTTP_201_CREATED)
