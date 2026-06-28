"""
Payment Operations REST surface — thin views over services.py.
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AmlAlert, B2BAccount, B2BInvoice, BnplInstalmentPlan,
    BnplProvider, BuyerWallet, BuyerWalletTransaction,
    ChargebackEvidence, ChargebackOutcome,
    CurrencyConversionDispute, FinancialReportSnapshot,
    FxHedgePosition, MultiCurrencyDisplay, PaymentFailureLog,
    PaymentMethodEligibilityRule, PaymentOpsEvent,
    PaymentOpsKpiSnapshot, PaymentRecoveryAttempt,
    ReconciliationException, SanctionsScreen, SarFiling,
    SellerAnnualTaxExport, SplitPaymentAllocation, StoreCredit,
    StoreCreditTransaction, TaxInvoice, TokenisedPaymentMethod,
    WalletTopUp,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH2 — Chargeback ─────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chargeback_evidence_add(request):
    obj = services.add_chargeback_evidence(
        chargeback_id=request.data.get('chargeback_id', ''),
        order_id=request.data.get('order_id', ''),
        kind=request.data.get('kind', 'other'),
        file_key=request.data.get('file_key', ''),
        notes=request.data.get('notes', ''),
        uploaded_by=request.user,
    )
    return Response({'evidence_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def chargeback_evidence_submit(request):
    n = services.submit_chargeback_evidence(
        chargeback_id=request.data.get('chargeback_id', ''),
        actor=request.user,
    )
    return Response({'submitted_count': n})


@api_view(['POST'])
@permission_classes([IsAdmin])
def chargeback_outcome_record(request):
    obj = services.record_chargeback_outcome(
        chargeback_id=request.data.get('chargeback_id', ''),
        outcome=request.data.get('outcome', 'pending'),
        recovery_amount=Decimal(str(request.data.get('recovery_amount', 0))),
        seller_liability=Decimal(str(request.data.get('seller_liability', 0))),
        platform_liability=Decimal(str(request.data.get('platform_liability', 0))),
        fee_charged=Decimal(str(request.data.get('fee_charged', 0))),
        currency=request.data.get('currency', 'AOA'),
        issuer_reference=request.data.get('issuer_reference', ''),
        notes=request.data.get('notes', ''),
    )
    return Response({'outcome': obj.outcome, 'recovery': str(obj.recovery_amount)})


# ─── CH3 — Reconciliation ─────────────────────────────────────

class ReconciliationQueueView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = ReconciliationException.objects.filter(resolved=False).values()[:200]
        return Response(list(rows))


@api_view(['POST'])
@permission_classes([IsAdmin])
def recon_resolve(request):
    ok = services.resolve_reconciliation_exception(
        exception_id=int(request.data.get('exception_id', 0)),
        resolver=request.user,
        resolution=request.data.get('resolution', ''),
    )
    return Response({'ok': ok})


# ─── CH4 — FX hedge ────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def fx_hedge_book(request):
    obj = services.book_fx_hedge(
        pair=request.data.get('pair', ''),
        side=request.data.get('side', 'buy'),
        notional=Decimal(str(request.data.get('notional', 0))),
        notional_currency=request.data.get('notional_currency', ''),
        booked_rate=Decimal(str(request.data.get('booked_rate', 0))),
        settle_at=request.data.get('settle_at') or timezone.now() + timezone.timedelta(days=30),
        counterparty=request.data.get('counterparty', ''),
    )
    return Response({'hedge_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def fx_hedge_settle(request):
    obj = get_object_or_404(FxHedgePosition, pk=request.data.get('hedge_id'))
    pnl = services.settle_fx_hedge(
        hedge=obj,
        settle_rate=Decimal(str(request.data.get('settle_rate', 0))),
    )
    return Response({'pnl': str(pnl), 'status': obj.status})


# ─── CH5 — Multi-currency display ─────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def display_price_snapshot(request):
    obj = services.snapshot_display_price(
        product_id=request.data.get('product_id', ''),
        base_currency=request.data.get('base_currency', 'USD'),
        base_amount=Decimal(str(request.data.get('base_amount', 0))),
        buyer_currency=request.data.get('buyer_currency', 'AOA'),
        fx_rate=Decimal(str(request.data.get('fx_rate', 0))),
        fx_markup_pct=Decimal(str(request.data.get('fx_markup_pct', 0))),
    )
    return Response({
        'display_amount': str(obj.display_amount),
        'currency': obj.buyer_currency,
        'fx_rate': str(obj.fx_rate),
    })


# ─── CH7 — Tax invoices ───────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tax_invoice_issue(request):
    buyer = None
    seller = None
    if request.data.get('buyer_id'):
        buyer = User.objects.filter(pk=request.data['buyer_id']).first()
    if request.data.get('seller_id'):
        seller = User.objects.filter(pk=request.data['seller_id']).first()
    obj = services.issue_tax_invoice(
        kind=request.data.get('kind', 'buyer_b2c'),
        order_id=request.data.get('order_id', ''),
        buyer=buyer, seller=seller,
        country=request.data.get('country', ''),
        currency=request.data.get('currency', 'AOA'),
        subtotal=Decimal(str(request.data.get('subtotal', 0))),
        tax_amount=Decimal(str(request.data.get('tax_amount', 0))),
        tax_breakdown=request.data.get('tax_breakdown') or [],
    )
    return Response({'invoice_id': str(obj.id),
                     'invoice_number': obj.invoice_number,
                     'total': str(obj.total)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def tax_invoice_void(request):
    inv = get_object_or_404(TaxInvoice, pk=request.data.get('invoice_id'))
    services.void_tax_invoice(inv, reason=request.data.get('reason', ''))
    return Response({'ok': True, 'voided': inv.voided})


# ─── CH9 — AML / SAR ──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def aml_alert_raise(request):
    user = get_object_or_404(User, pk=request.data.get('subject_user_id'))
    obj = services.raise_aml_alert(
        subject_user=user,
        kind=request.data.get('kind', 'velocity_anomaly'),
        severity=int(request.data.get('severity', 50)),
        total_amount=Decimal(str(request.data.get('total_amount', 0))),
        currency=request.data.get('currency', 'AOA'),
        transaction_ids=request.data.get('transaction_ids') or [],
        evidence=request.data.get('evidence') or {},
    )
    return Response({'alert_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def aml_escalate_sar(request):
    alert = get_object_or_404(AmlAlert, pk=request.data.get('alert_id'))
    sar = services.escalate_to_sar(
        alert=alert, filer=request.user,
        narrative=request.data.get('narrative', ''),
    )
    return Response({'sar_reference': sar.sar_reference,
                     'status': sar.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def sar_file(request):
    sar = get_object_or_404(SarFiling, pk=request.data.get('sar_id'))
    services.file_sar(sar, fiu_reference=request.data.get('fiu_reference', ''))
    return Response({'ok': True, 'status': sar.status})


# ─── CH10 — Annual tax export ────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def annual_tax_export_generate(request):
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    obj = services.generate_annual_tax_export(
        seller=seller, tax_year=int(request.data.get('tax_year', timezone.now().year)),
        currency=request.data.get('currency', 'USD'),
    )
    return Response({
        'gross_sales': str(obj.gross_sales),
        'commissions_paid': str(obj.commissions_paid),
        'net_payouts': str(obj.net_payouts),
    })


# ─── CH11 — Payment method eligibility ────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def payment_methods_eligible(request):
    result = services.eligible_payment_methods(
        country=request.data.get('country', ''),
        currency=request.data.get('currency', 'AOA'),
        amount=Decimal(str(request.data.get('amount', 0))),
        buyer_segment=request.data.get('buyer_segment', ''),
    )
    return Response({'methods': result})


# ─── CH12 — BNPL ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bnpl_create_plan(request):
    provider = get_object_or_404(BnplProvider, code=request.data.get('provider_code'))
    try:
        plan = services.create_bnpl_plan(
            provider=provider, order_id=request.data.get('order_id', ''),
            buyer=request.user,
            total_amount=Decimal(str(request.data.get('total_amount', 0))),
            currency=request.data.get('currency', 'AOA'),
            instalments=int(request.data.get('instalments', 4)),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'plan_id': str(plan.id),
                     'instalment_amount': str(plan.instalment_amount),
                     'next_due_at': plan.next_due_at.isoformat()},
                    status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def bnpl_mark_paid(request):
    plan = get_object_or_404(BnplInstalmentPlan, pk=request.data.get('plan_id'))
    ok = services.mark_bnpl_paid(
        plan=plan, instalment_seq=int(request.data.get('instalment_seq', 0)),
    )
    return Response({'ok': ok, 'status': plan.status})


# ─── CH13 — Store credit ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def store_credit_grant(request):
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    obj = services.grant_store_credit(
        user=user,
        amount=Decimal(str(request.data.get('amount', 0))),
        reason=request.data.get('reason', 'manual_admin'),
        currency=request.data.get('currency', 'AOA'),
        related_order_id=request.data.get('related_order_id', ''),
        granted_by=request.user,
        expires_in_days=int(request.data.get('expires_in_days', 365)),
    )
    return Response({'credit_id': str(obj.id),
                     'expires_at': obj.expires_at.isoformat()}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def store_credit_spend(request):
    try:
        result = services.spend_store_credit(
            user=request.user,
            amount=Decimal(str(request.data.get('amount', 0))),
            order_id=request.data.get('order_id', ''),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response(result)


class MyStoreCreditView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = StoreCredit.objects.filter(
            user=request.user, status='active',
        ).values('id', 'remaining_amount', 'currency',
                 'reason', 'expires_at', 'created_at')
        total = sum(Decimal(str(r['remaining_amount'])) for r in rows)
        return Response({'credits': list(rows), 'total_remaining': str(total)})


# ─── CH15 — B2B ────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def b2b_account_approve(request):
    account = get_object_or_404(B2BAccount, pk=request.data.get('account_id'))
    services.approve_b2b_account(
        account=account, approver=request.user,
        credit_limit=Decimal(str(request.data.get('credit_limit', 0))),
        terms_days=int(request.data.get('terms_days', 30)),
    )
    return Response({'status': account.status,
                     'available_credit': str(account.available_credit)})


@api_view(['POST'])
@permission_classes([IsAdmin])
def b2b_invoice_issue(request):
    account = get_object_or_404(B2BAccount, pk=request.data.get('account_id'))
    try:
        invoice = services.issue_b2b_invoice(
            account=account,
            order_id=request.data.get('order_id', ''),
            amount=Decimal(str(request.data.get('amount', 0))),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'invoice_id': str(invoice.id),
                     'invoice_number': invoice.invoice_number,
                     'due_at': invoice.due_at.isoformat()}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def b2b_invoice_pay(request):
    invoice = get_object_or_404(B2BInvoice, pk=request.data.get('invoice_id'))
    services.pay_b2b_invoice(
        invoice, amount=Decimal(str(request.data.get('amount', 0))),
    )
    return Response({'status': invoice.status})


# ─── CH16 — Split payment ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def split_allocate(request):
    rows = services.allocate_split_payment(
        order_id=request.data.get('order_id', ''),
        allocations=request.data.get('allocations') or [],
    )
    return Response({'allocations': [{'id': r.pk, 'sequence': r.sequence_number,
                                       'amount': str(r.amount),
                                       'method': r.method_code} for r in rows]},
                    status=201)


# ─── CH18 — Wallet ─────────────────────────────────────────────

class MyWalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = services.get_or_create_wallet(request.user)
        recent = BuyerWalletTransaction.objects.filter(wallet=wallet).values(
            'kind', 'amount', 'currency', 'balance_after',
            'related_order_id', 'occurred_at',
        )[:50]
        return Response({
            'available_balance': str(wallet.available_balance),
            'currency': wallet.currency,
            'daily_spend_limit': str(wallet.daily_spend_limit),
            'recent_transactions': list(recent),
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wallet_topup_create(request):
    topup = services.topup_wallet(
        user=request.user,
        amount=Decimal(str(request.data.get('amount', 0))),
        gateway=request.data.get('gateway', 'multicaixa_express'),
        intent_id=request.data.get('intent_id', ''),
        currency=request.data.get('currency'),
    )
    return Response({'topup_id': str(topup.id),
                     'status': topup.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def wallet_topup_confirm(request):
    topup = get_object_or_404(WalletTopUp, pk=request.data.get('topup_id'))
    services.confirm_topup(topup)
    return Response({'status': topup.status,
                     'balance_after': str(topup.wallet.available_balance)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wallet_spend(request):
    try:
        tx = services.spend_wallet(
            user=request.user,
            amount=Decimal(str(request.data.get('amount', 0))),
            order_id=request.data.get('order_id', ''),
        )
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'tx_id': tx.pk, 'balance_after': str(tx.balance_after)})


# ─── CH19 — Payment failures + recovery ───────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def payment_failure_record(request):
    user = get_object_or_404(User, pk=request.data.get('buyer_id'))
    obj = services.record_payment_failure(
        order_id=request.data.get('order_id', ''),
        buyer=user,
        category=request.data.get('category', 'other'),
        failure_code=request.data.get('failure_code', ''),
        failure_message=request.data.get('failure_message', ''),
        amount=Decimal(str(request.data.get('amount', 0))),
        currency=request.data.get('currency', 'AOA'),
        gateway=request.data.get('gateway', ''),
        method_code=request.data.get('method_code', ''),
        intent_id=request.data.get('intent_id', ''),
    )
    return Response({'failure_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def recovery_attempt_execute(request):
    attempt = get_object_or_404(PaymentRecoveryAttempt,
                                pk=request.data.get('attempt_id'))
    services.execute_recovery_attempt(
        attempt,
        outcome=request.data.get('outcome', 'pending'),
        new_intent_id=request.data.get('new_intent_id', ''),
        notes=request.data.get('notes', ''),
    )
    return Response({'outcome': attempt.outcome})


# ─── CH20 — FX dispute ────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def fx_dispute_file(request):
    obj = services.file_fx_dispute(
        order_id=request.data.get('order_id', ''),
        buyer=request.user,
        displayed_amount=Decimal(str(request.data.get('displayed_amount', 0))),
        displayed_currency=request.data.get('displayed_currency', ''),
        charged_amount=Decimal(str(request.data.get('charged_amount', 0))),
        charged_currency=request.data.get('charged_currency', ''),
        booked_fx_rate=Decimal(str(request.data.get('booked_fx_rate', 0))),
        expected_fx_rate=Decimal(str(request.data.get('expected_fx_rate', 0))),
    )
    return Response({'dispute_id': str(obj.id),
                     'difference': str(obj.difference)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def fx_dispute_resolve(request):
    obj = get_object_or_404(CurrencyConversionDispute,
                            pk=request.data.get('dispute_id'))
    services.resolve_fx_dispute(
        obj,
        outcome=request.data.get('outcome', 'explained'),
        notes=request.data.get('notes', ''),
    )
    return Response({'status': obj.status})


# ─── CH21 — Financial report ──────────────────────────────────

class FinancialReportView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = FinancialReportSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_financial_report(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'gmv': str(snap.gmv),
            'net_revenue': str(snap.net_revenue),
            'commission_revenue': str(snap.commission_revenue),
            'refund_amount': str(snap.refund_amount),
            'refund_rate': snap.refund_rate,
            'chargeback_amount': str(snap.chargeback_amount),
            'chargeback_rate': snap.chargeback_rate,
            'gross_profit': str(snap.gross_profit),
        })


# ─── CH22 — Sanctions ─────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sanctions_screen(request):
    obj = services.screen_for_sanctions(
        subject_user=request.user,
        name=request.data.get('name', ''),
        country=request.data.get('country', ''),
        context=request.data.get('context', 'checkout'),
    )
    if not obj:
        return Response({'hit': False})
    return Response({'hit': True, 'screen_id': obj.pk,
                     'action_taken': obj.action_taken,
                     'confidence': obj.match_confidence})


# ─── CH23 — Tokenisation ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def token_register(request):
    obj = services.register_tokenised_method(
        user=request.user,
        gateway=request.data.get('gateway', ''),
        method_type=request.data.get('method_type', 'card'),
        gateway_token=request.data.get('gateway_token', ''),
        brand=request.data.get('brand', ''),
        last_four=request.data.get('last_four', ''),
        expiry_month=request.data.get('expiry_month'),
        expiry_year=request.data.get('expiry_year'),
        three_ds_supported=bool(request.data.get('three_ds_supported', True)),
    )
    return Response({'token_id': str(obj.id),
                     'last_four': obj.last_four,
                     'brand': obj.brand}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def token_revoke(request):
    obj = get_object_or_404(TokenisedPaymentMethod,
                            pk=request.data.get('token_id'),
                            user=request.user)
    ok = services.revoke_tokenised_method(obj)
    return Response({'ok': ok})


# ─── CH24 — KPI ───────────────────────────────────────────────

class PaymentOpsKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = PaymentOpsKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_payment_ops_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'transaction_count': snap.transaction_count,
            'transaction_value': str(snap.transaction_value),
            'auth_rate_pct': snap.auth_rate_pct,
            'failure_rate_pct': snap.failure_rate_pct,
            'chargeback_rate_pct': snap.chargeback_rate_pct,
            'chargeback_win_rate_pct': snap.chargeback_win_rate_pct,
            'refund_rate_pct': snap.refund_rate_pct,
            'fx_pnl': str(snap.fx_pnl),
            'bnpl_default_rate_pct': snap.bnpl_default_rate_pct,
            'wallet_topups_total': str(snap.wallet_topups_total),
            'sanctions_blocks': snap.sanctions_blocks,
            'aml_alerts_open': snap.aml_alerts_open,
            'sar_filings': snap.sar_filings,
            'recon_exceptions_open': snap.recon_exceptions_open,
            'b2b_overdue_amount': str(snap.b2b_overdue_amount),
            'by_gateway': snap.by_gateway,
        })
