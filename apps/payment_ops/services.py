"""
Payment Operations — domain services.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .models import (
    AmlAlert, B2BAccount, B2BInvoice, BnplInstalment,
    BnplInstalmentPlan, BnplProvider, BuyerWallet,
    BuyerWalletTransaction, ChargebackEvidence, ChargebackOutcome,
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
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH2 — Chargeback evidence + outcome
# ═══════════════════════════════════════════════════════════════════

def add_chargeback_evidence(*, chargeback_id: str, order_id: str,
                              kind: str, file_key: str = '',
                              notes: str = '', uploaded_by=None) -> ChargebackEvidence:
    obj = ChargebackEvidence.objects.create(
        chargeback_id=chargeback_id[:64], order_id=order_id[:64],
        kind=kind, file_key=file_key[:255], notes=notes,
        uploaded_by=uploaded_by,
    )
    PaymentOpsEvent.log(
        kind='chargeback.evidence_added',
        order_id=order_id, actor=uploaded_by,
        payload={'chargeback_id': chargeback_id, 'evidence_kind': kind},
    )
    return obj


def submit_chargeback_evidence(*, chargeback_id: str, actor=None) -> int:
    """Mark every evidence row as submitted (atomic for audit)."""
    n = ChargebackEvidence.objects.filter(
        chargeback_id=chargeback_id, submitted_at__isnull=True,
    ).update(submitted_at=timezone.now())
    PaymentOpsEvent.log(
        kind='chargeback.evidence_submitted',
        actor=actor, payload={'chargeback_id': chargeback_id, 'count': n},
    )
    return n


def record_chargeback_outcome(*, chargeback_id: str, outcome: str,
                                recovery_amount: Decimal = Decimal('0'),
                                seller_liability: Decimal = Decimal('0'),
                                platform_liability: Decimal = Decimal('0'),
                                fee_charged: Decimal = Decimal('0'),
                                currency: str = 'AOA',
                                issuer_reference: str = '',
                                notes: str = '') -> ChargebackOutcome:
    obj, _ = ChargebackOutcome.objects.update_or_create(
        chargeback_id=chargeback_id[:64],
        defaults={
            'outcome': outcome,
            'recovery_amount': recovery_amount,
            'seller_liability_amount': seller_liability,
            'platform_liability_amount': platform_liability,
            'fee_charged': fee_charged, 'currency': currency,
            'issuer_reference': issuer_reference[:120],
            'notes': notes[:5000],
            'decided_at': timezone.now(),
        },
    )
    PaymentOpsEvent.log(
        kind=f'chargeback.{outcome}',
        payload={'chargeback_id': chargeback_id,
                 'recovery_amount': str(recovery_amount),
                 'seller_liability': str(seller_liability)},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH3 — Reconciliation exception queue
# ═══════════════════════════════════════════════════════════════════

def record_reconciliation_exception(*, settlement_date,
                                       kind: str,
                                       psp_reference: str = '',
                                       order_id: str = '',
                                       expected: Decimal = None,
                                       actual: Decimal = None,
                                       currency: str = '',
                                       raw_row: dict = None) -> ReconciliationException:
    return ReconciliationException.objects.create(
        settlement_date=settlement_date,
        kind=kind, psp_reference=psp_reference[:120],
        order_id=order_id[:64],
        expected_amount=expected, actual_amount=actual,
        currency=currency[:3], raw_row=raw_row or {},
    )


def resolve_reconciliation_exception(exception_id: int, *,
                                       resolver, resolution: str) -> bool:
    obj = ReconciliationException.objects.filter(pk=exception_id).first()
    if not obj or obj.resolved:
        return False
    obj.resolved = True
    obj.resolution = resolution[:120]
    obj.resolved_by = resolver
    obj.resolved_at = timezone.now()
    obj.save(update_fields=['resolved', 'resolution',
                             'resolved_by', 'resolved_at'])
    PaymentOpsEvent.log(
        kind='recon.exception_resolved',
        actor=resolver, order_id=obj.order_id,
        payload={'exception_id': exception_id, 'resolution': resolution},
    )
    return True


# ═══════════════════════════════════════════════════════════════════
# CH4 — FX hedge book
# ═══════════════════════════════════════════════════════════════════

def book_fx_hedge(*, pair: str, side: str, notional: Decimal,
                    notional_currency: str, booked_rate: Decimal,
                    settle_at, counterparty: str = '') -> FxHedgePosition:
    return FxHedgePosition.objects.create(
        pair=pair[:8], side=side, notional=notional,
        notional_currency=notional_currency[:3],
        booked_rate=booked_rate, counterparty=counterparty[:80],
        settle_at=settle_at,
    )


def settle_fx_hedge(*, hedge: FxHedgePosition,
                     settle_rate: Decimal) -> Decimal:
    """Mark position settled and compute P&L.  PnL = notional * (booked - settle)
    for SELL; opposite sign for BUY."""
    pnl_per_unit = hedge.booked_rate - settle_rate
    if hedge.side == 'buy':
        pnl_per_unit = -pnl_per_unit
    pnl = (Decimal(str(hedge.notional)) * pnl_per_unit).quantize(Decimal('0.01'))
    hedge.settle_rate = settle_rate
    hedge.pnl = pnl
    hedge.status = 'settled'
    hedge.settled_at = timezone.now()
    hedge.save(update_fields=['settle_rate', 'pnl', 'status', 'settled_at'])
    return pnl


# ═══════════════════════════════════════════════════════════════════
# CH5 — Multi-currency display
# ═══════════════════════════════════════════════════════════════════

def snapshot_display_price(*, product_id: str, base_currency: str,
                              base_amount: Decimal,
                              buyer_currency: str,
                              fx_rate: Decimal,
                              fx_markup_pct: Decimal = Decimal('0')) -> MultiCurrencyDisplay:
    display = (Decimal(str(base_amount)) * Decimal(str(fx_rate)) *
               (Decimal(100) + Decimal(str(fx_markup_pct))) / Decimal(100))
    return MultiCurrencyDisplay.objects.create(
        product_id=product_id[:64],
        base_currency=base_currency[:3], base_amount=base_amount,
        buyer_currency=buyer_currency[:3],
        display_amount=display.quantize(Decimal('0.01')),
        fx_rate=fx_rate, fx_markup_pct=fx_markup_pct,
    )


# ═══════════════════════════════════════════════════════════════════
# CH7 — Tax invoice
# ═══════════════════════════════════════════════════════════════════

def issue_tax_invoice(*, kind: str, order_id: str = '',
                        buyer=None, seller=None,
                        country: str = '',
                        currency: str = 'AOA',
                        subtotal: Decimal,
                        tax_amount: Decimal,
                        tax_breakdown: list = None,
                        file_key: str = '') -> TaxInvoice:
    invoice_number = _make_invoice_number(kind)
    total = subtotal + tax_amount
    obj = TaxInvoice.objects.create(
        invoice_number=invoice_number, kind=kind,
        order_id=order_id[:64], buyer=buyer, seller=seller,
        country=country[:2], currency=currency[:3],
        subtotal=subtotal, tax_amount=tax_amount, total=total,
        tax_breakdown=tax_breakdown or [], file_key=file_key[:255],
    )
    PaymentOpsEvent.log(
        kind='tax.invoice_issued', user=buyer or seller,
        order_id=order_id,
        payload={'invoice_number': invoice_number, 'total': str(total)},
    )
    return obj


def void_tax_invoice(invoice: TaxInvoice, *, reason: str) -> TaxInvoice:
    """Issue a credit-note + flag the original as voided."""
    if invoice.voided:
        return invoice
    invoice.voided = True
    invoice.voided_reason = reason[:120]
    invoice.save(update_fields=['voided', 'voided_reason'])
    issue_tax_invoice(
        kind='credit_note', order_id=invoice.order_id,
        buyer=invoice.buyer, seller=invoice.seller,
        country=invoice.country, currency=invoice.currency,
        subtotal=-invoice.subtotal, tax_amount=-invoice.tax_amount,
        tax_breakdown=invoice.tax_breakdown,
    )
    return invoice


def _make_invoice_number(kind: str) -> str:
    prefix = {
        'buyer_b2c': 'B2C',
        'buyer_b2b': 'B2B',
        'seller_comm': 'COM',
        'credit_note': 'CN',
    }.get(kind, 'INV')
    return f'{prefix}-{timezone.now().strftime("%Y%m")}-{secrets.token_hex(4).upper()}'


# ═══════════════════════════════════════════════════════════════════
# CH9 — AML alert + SAR filing
# ═══════════════════════════════════════════════════════════════════

def raise_aml_alert(*, subject_user, kind: str,
                      severity: int = 50,
                      total_amount: Decimal = Decimal('0'),
                      currency: str = 'AOA',
                      transaction_ids: list = None,
                      evidence: dict = None) -> AmlAlert:
    obj = AmlAlert.objects.create(
        subject_user=subject_user, kind=kind,
        severity=severity, total_amount=total_amount,
        currency=currency[:3],
        transaction_ids=transaction_ids or [],
        evidence=evidence or {},
    )
    PaymentOpsEvent.log(
        kind='aml.alert_raised', user=subject_user,
        payload={'alert_id': str(obj.id), 'kind': kind, 'severity': severity},
    )
    return obj


def escalate_to_sar(*, alert: AmlAlert, filer,
                      narrative: str) -> SarFiling:
    """Move an open AML alert to SAR filing.  Idempotent — second
    call returns the existing filing."""
    existing = SarFiling.objects.filter(alert=alert).first()
    if existing:
        return existing
    alert.status = 'escalated'
    alert.save(update_fields=['status'])
    sar_ref = f'SAR-{timezone.now().strftime("%Y%m%d")}-{secrets.token_hex(4).upper()}'
    sar = SarFiling.objects.create(
        alert=alert, sar_reference=sar_ref,
        narrative=narrative, filer=filer,
    )
    PaymentOpsEvent.log(
        kind='aml.sar_drafted', actor=filer,
        payload={'sar_reference': sar_ref, 'alert_id': str(alert.id)},
    )
    return sar


def file_sar(sar: SarFiling, *, fiu_reference: str) -> SarFiling:
    sar.status = 'filed'
    sar.fiu_reference = fiu_reference[:120]
    sar.filed_at = timezone.now()
    sar.save(update_fields=['status', 'fiu_reference', 'filed_at'])
    PaymentOpsEvent.log(
        kind='aml.sar_filed',
        payload={'sar_reference': sar.sar_reference,
                 'fiu_reference': fiu_reference},
    )
    return sar


# ═══════════════════════════════════════════════════════════════════
# CH10 — Annual seller tax export
# ═══════════════════════════════════════════════════════════════════

def generate_annual_tax_export(*, seller, tax_year: int,
                                  currency: str = 'USD') -> SellerAnnualTaxExport:
    """Compute the seller's annual summary. Sourced from existing
    orders + payments + chargebacks tables; we tolerate any of those
    missing in dev."""
    year_start = date_cls(tax_year, 1, 1)
    year_end = date_cls(tax_year, 12, 31)
    gross = Decimal('0')
    refunds = Decimal('0')
    commissions = Decimal('0')
    chargebacks = Decimal('0')
    try:
        from apps.orders.models import Order
        agg = Order.objects.filter(
            items__product__store__owner=seller,
            created_at__date__gte=year_start,
            created_at__date__lte=year_end,
        ).aggregate(s=django_models.Sum('total_amount'))
        gross = Decimal(str(agg['s'] or 0))
    except Exception:
        pass
    try:
        from apps.payments.models import PlatformCommission
        agg = PlatformCommission.objects.filter(
            seller=seller, created_at__date__gte=year_start,
            created_at__date__lte=year_end,
        ).aggregate(s=django_models.Sum('amount'))
        commissions = Decimal(str(agg['s'] or 0))
    except Exception:
        pass

    net = gross - refunds - commissions - chargebacks
    obj, _ = SellerAnnualTaxExport.objects.update_or_create(
        seller=seller, tax_year=tax_year,
        defaults={
            'gross_sales': gross, 'refunds_issued': refunds,
            'commissions_paid': commissions,
            'chargebacks_lost': chargebacks, 'net_payouts': net,
            'currency': currency,
        },
    )
    PaymentOpsEvent.log(
        kind='tax.annual_export_generated', user=seller,
        payload={'tax_year': tax_year, 'net': str(net)},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH11 — Payment method eligibility
# ═══════════════════════════════════════════════════════════════════

def eligible_payment_methods(*, country: str, currency: str,
                                amount: Decimal,
                                buyer_segment: str = '') -> list[dict]:
    """Walk rules in priority order; first match per method_code wins.
    Returns the list of allow-rules that match."""
    rules = list(
        PaymentMethodEligibilityRule.objects.filter(is_active=True)
        .filter(
            django_models.Q(country__iexact=country) | django_models.Q(country='')
        ).filter(
            django_models.Q(currency__iexact=currency) | django_models.Q(currency='')
        ).order_by('priority')
    )
    chosen = {}
    for r in rules:
        if r.method_code in chosen:
            continue
        if amount < r.min_order_value:
            continue
        if r.max_order_value and amount > r.max_order_value:
            continue
        if r.buyer_segment and r.buyer_segment != buyer_segment:
            continue
        chosen[r.method_code] = r
    return [{'method_code': r.method_code, 'allow': r.allow,
              'reason': r.reason, 'priority': r.priority}
             for r in chosen.values() if r.allow]


# ═══════════════════════════════════════════════════════════════════
# CH12 — BNPL
# ═══════════════════════════════════════════════════════════════════

def create_bnpl_plan(*, provider: BnplProvider, order_id: str,
                       buyer, total_amount: Decimal,
                       currency: str, instalments: int = 4,
                       first_due_at=None) -> BnplInstalmentPlan:
    if instalments <= 0:
        raise ValueError('INSTALMENTS_INVALID')
    if total_amount > provider.max_order_value:
        raise ValueError('AMOUNT_OVER_LIMIT')
    per = (Decimal(str(total_amount)) / Decimal(instalments)).quantize(Decimal('0.01'))
    first_due_at = first_due_at or (timezone.now() + timedelta(days=14))
    plan = BnplInstalmentPlan.objects.create(
        provider=provider, order_id=order_id[:64], buyer=buyer,
        total_amount=total_amount, currency=currency[:3],
        instalments=instalments, instalment_amount=per,
        next_due_at=first_due_at,
        status='active',
    )
    for i in range(instalments):
        BnplInstalment.objects.create(
            plan=plan, sequence_number=i + 1,
            amount=per,
            due_at=first_due_at + timedelta(days=30 * i),
        )
    PaymentOpsEvent.log(
        kind='bnpl.plan_created', user=buyer, order_id=order_id,
        payload={'plan_id': str(plan.id), 'provider': provider.code,
                 'amount': str(total_amount), 'instalments': instalments},
    )
    return plan


def mark_bnpl_paid(plan: BnplInstalmentPlan, *,
                    instalment_seq: int) -> bool:
    inst = BnplInstalment.objects.filter(
        plan=plan, sequence_number=instalment_seq,
    ).first()
    if not inst or inst.status == 'paid':
        return False
    inst.status = 'paid'
    inst.paid_at = timezone.now()
    inst.days_late = max(0, (inst.paid_at - inst.due_at).days)
    inst.save(update_fields=['status', 'paid_at', 'days_late'])
    plan.instalments_paid += 1
    if inst.days_late > 0:
        plan.instalments_late += 1
    if plan.instalments_paid >= plan.instalments:
        plan.status = 'completed'
    else:
        nxt = BnplInstalment.objects.filter(
            plan=plan, status='due',
        ).order_by('sequence_number').first()
        if nxt:
            plan.next_due_at = nxt.due_at
    plan.save()
    return True


# ═══════════════════════════════════════════════════════════════════
# CH13 — Store credit
# ═══════════════════════════════════════════════════════════════════

def grant_store_credit(*, user, amount: Decimal, reason: str,
                         currency: str = 'AOA',
                         related_order_id: str = '',
                         granted_by=None,
                         expires_in_days: int = 365) -> StoreCredit:
    obj = StoreCredit.objects.create(
        user=user, initial_amount=amount,
        remaining_amount=amount, currency=currency[:3],
        reason=reason, related_order_id=related_order_id[:64],
        granted_by=granted_by,
        expires_at=timezone.now() + timedelta(days=expires_in_days),
    )
    PaymentOpsEvent.log(
        kind='store_credit.granted', user=user, actor=granted_by,
        order_id=related_order_id,
        payload={'credit_id': str(obj.id), 'amount': str(amount),
                 'reason': reason},
    )
    return obj


@transaction.atomic
def spend_store_credit(*, user, amount: Decimal,
                          order_id: str = '') -> dict:
    """FIFO debit across active credit rows. Returns the per-credit
    debit breakdown so the order accounting can attribute each
    portion correctly."""
    available = list(
        StoreCredit.objects.select_for_update().filter(
            user=user, status='active', remaining_amount__gt=0,
            expires_at__gt=timezone.now(),
        ).order_by('expires_at', 'created_at')
    )
    remaining = Decimal(str(amount))
    debits = []
    for credit in available:
        if remaining <= 0:
            break
        take = min(credit.remaining_amount, remaining)
        credit.remaining_amount -= take
        if credit.remaining_amount <= 0:
            credit.status = 'depleted'
        credit.save(update_fields=['remaining_amount', 'status'])
        StoreCreditTransaction.objects.create(
            credit=credit, kind='debit', amount=take,
            related_order_id=order_id[:64],
        )
        debits.append({'credit_id': str(credit.id),
                       'debit_amount': str(take)})
        remaining -= take
    if remaining > 0:
        raise ValueError(f'INSUFFICIENT_CREDIT shortage={remaining}')
    return {'debits': debits, 'total': str(amount)}


# ═══════════════════════════════════════════════════════════════════
# CH15 — B2B
# ═══════════════════════════════════════════════════════════════════

def approve_b2b_account(*, account: B2BAccount, approver,
                          credit_limit: Decimal,
                          terms_days: int = 30) -> B2BAccount:
    account.credit_limit = credit_limit
    account.available_credit = credit_limit
    account.payment_terms_days = terms_days
    account.status = 'approved'
    account.approved_at = timezone.now()
    account.approved_by = approver
    account.save()
    PaymentOpsEvent.log(
        kind='b2b.account_approved', actor=approver,
        payload={'account_id': str(account.id),
                 'credit_limit': str(credit_limit)},
    )
    return account


@transaction.atomic
def issue_b2b_invoice(*, account: B2BAccount, order_id: str,
                       amount: Decimal,
                       currency: str = None) -> B2BInvoice:
    locked = B2BAccount.objects.select_for_update().get(pk=account.pk)
    if locked.status != 'approved':
        raise ValueError('ACCOUNT_NOT_APPROVED')
    if locked.available_credit < amount:
        raise ValueError('CREDIT_LIMIT_EXCEEDED')
    locked.available_credit -= amount
    locked.save(update_fields=['available_credit'])
    invoice_number = _make_invoice_number('buyer_b2b')
    invoice = B2BInvoice.objects.create(
        account=locked, order_id=order_id[:64],
        invoice_number=invoice_number,
        due_at=timezone.now() + timedelta(days=locked.payment_terms_days),
        amount=amount, currency=currency or locked.currency,
    )
    PaymentOpsEvent.log(
        kind='b2b.invoice_issued',
        payload={'invoice_id': str(invoice.id),
                 'amount': str(amount),
                 'due_at': invoice.due_at.isoformat()},
    )
    return invoice


@transaction.atomic
def pay_b2b_invoice(invoice: B2BInvoice, *,
                      amount: Decimal) -> B2BInvoice:
    locked = B2BInvoice.objects.select_for_update().get(pk=invoice.pk)
    locked.paid_amount += amount
    if locked.paid_amount >= locked.amount:
        locked.status = 'paid'
        locked.paid_at = timezone.now()
    locked.save(update_fields=['paid_amount', 'status', 'paid_at'])
    # Free the corresponding credit.
    acct = B2BAccount.objects.select_for_update().get(pk=locked.account_id)
    acct.available_credit = min(acct.credit_limit,
                                 acct.available_credit + amount)
    acct.save(update_fields=['available_credit'])
    return locked


# ═══════════════════════════════════════════════════════════════════
# CH16 — Split payment
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def allocate_split_payment(*, order_id: str,
                              allocations: list[dict]) -> list[SplitPaymentAllocation]:
    """`allocations` shape:
       [{method_code, amount, currency, intent_id?}].
       The sum must equal the order total — caller responsibility."""
    out = []
    for i, alloc in enumerate(allocations):
        obj, _ = SplitPaymentAllocation.objects.update_or_create(
            order_id=order_id[:64], sequence_number=i + 1,
            defaults={
                'method_code': alloc['method_code'][:40],
                'amount': Decimal(str(alloc['amount'])),
                'currency': alloc['currency'][:3],
                'intent_id': alloc.get('intent_id', '')[:80],
                'status': 'pending',
            },
        )
        out.append(obj)
    return out


def update_split_allocation_status(allocation: SplitPaymentAllocation, *,
                                      new_status: str,
                                      failure_code: str = '') -> bool:
    allocation.status = new_status
    allocation.failure_code = failure_code[:40]
    allocation.save(update_fields=['status', 'failure_code'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH18 — Buyer wallet
# ═══════════════════════════════════════════════════════════════════

def get_or_create_wallet(user, *, currency: str = 'AOA') -> BuyerWallet:
    obj, _ = BuyerWallet.objects.get_or_create(
        user=user, defaults={'currency': currency[:3]},
    )
    return obj


@transaction.atomic
def topup_wallet(*, user, amount: Decimal,
                   gateway: str = 'multicaixa_express',
                   intent_id: str = '',
                   currency: str = None) -> WalletTopUp:
    wallet = get_or_create_wallet(user)
    return WalletTopUp.objects.create(
        wallet=wallet, amount=amount,
        currency=(currency or wallet.currency)[:3],
        gateway=gateway[:24], intent_id=intent_id[:80],
    )


@transaction.atomic
def confirm_topup(topup: WalletTopUp) -> BuyerWalletTransaction:
    if topup.status == 'succeeded':
        return None
    wallet = BuyerWallet.objects.select_for_update().get(pk=topup.wallet_id)
    wallet.available_balance += topup.amount
    wallet.save(update_fields=['available_balance', 'updated_at'])
    topup.status = 'succeeded'
    topup.completed_at = timezone.now()
    topup.save(update_fields=['status', 'completed_at'])
    tx = BuyerWalletTransaction.objects.create(
        wallet=wallet, kind='top_up', amount=topup.amount,
        currency=topup.currency,
        balance_after=wallet.available_balance,
        reference=f'topup:{topup.id}', intent_id=topup.intent_id,
    )
    PaymentOpsEvent.log(
        kind='wallet.topup_succeeded', user=wallet.user,
        payload={'amount': str(topup.amount),
                 'balance_after': str(wallet.available_balance)},
    )
    return tx


@transaction.atomic
def spend_wallet(*, user, amount: Decimal,
                   order_id: str = '') -> BuyerWalletTransaction:
    wallet = BuyerWallet.objects.select_for_update().get(user=user)
    if not wallet.is_active:
        raise ValueError('WALLET_INACTIVE')
    if wallet.available_balance < amount:
        raise ValueError('INSUFFICIENT_BALANCE')
    # Daily / monthly limit.
    today = timezone.now().date()
    daily_spend = (
        BuyerWalletTransaction.objects.filter(
            wallet=wallet, kind='spend',
            occurred_at__date=today,
        ).aggregate(s=django_models.Sum('amount'))['s'] or Decimal('0')
    )
    if daily_spend + amount > wallet.daily_spend_limit:
        raise ValueError('DAILY_LIMIT_EXCEEDED')
    wallet.available_balance -= amount
    wallet.save(update_fields=['available_balance', 'updated_at'])
    tx = BuyerWalletTransaction.objects.create(
        wallet=wallet, kind='spend', amount=amount,
        currency=wallet.currency,
        balance_after=wallet.available_balance,
        related_order_id=order_id[:64],
    )
    return tx


# ═══════════════════════════════════════════════════════════════════
# CH19 — Payment failure + recovery
# ═══════════════════════════════════════════════════════════════════

_RECOVERY_STRATEGY_BY_CATEGORY = {
    'insufficient_funds': 'split_payment',
    'card_declined':      'retry_other_method',
    'do_not_honour':      'retry_other_method',
    'expired_card':       'manual_intervention',
    'fraud_suspected':    'manual_intervention',
    '3ds_failed':         'soft_decline_retry',
    'network_error':      'retry_same_method',
    'limit_exceeded':     'split_payment',
    'country_blocked':    'retry_other_method',
    'other':              'email_nudge',
}


def record_payment_failure(*, order_id: str, buyer,
                              category: str,
                              failure_code: str = '',
                              failure_message: str = '',
                              amount: Decimal, currency: str = 'AOA',
                              gateway: str = '',
                              method_code: str = '',
                              intent_id: str = '') -> PaymentFailureLog:
    obj = PaymentFailureLog.objects.create(
        order_id=order_id[:64], buyer=buyer,
        intent_id=intent_id[:80], gateway=gateway[:24],
        method_code=method_code[:40], category=category,
        failure_code=failure_code[:40],
        failure_message=failure_message[:255],
        amount=amount, currency=currency[:3],
    )
    # Auto-schedule the first recovery attempt.
    strategy = _RECOVERY_STRATEGY_BY_CATEGORY.get(category, 'email_nudge')
    PaymentRecoveryAttempt.objects.create(
        failure=obj, strategy=strategy,
        scheduled_at=timezone.now() + timedelta(hours=1),
    )
    PaymentOpsEvent.log(
        kind='payment.failed', user=buyer, order_id=order_id,
        payload={'category': category, 'amount': str(amount),
                 'strategy': strategy},
    )
    return obj


def execute_recovery_attempt(attempt: PaymentRecoveryAttempt, *,
                                outcome: str,
                                new_intent_id: str = '',
                                notes: str = '') -> bool:
    attempt.executed_at = timezone.now()
    attempt.outcome = outcome
    attempt.new_intent_id = new_intent_id[:80]
    attempt.notes = notes[:5000]
    attempt.save()
    PaymentOpsEvent.log(
        kind=f'payment.recovery_{outcome}',
        payload={'strategy': attempt.strategy,
                 'attempt': attempt.attempt_number},
    )
    return True


# ═══════════════════════════════════════════════════════════════════
# CH20 — FX dispute
# ═══════════════════════════════════════════════════════════════════

def file_fx_dispute(*, order_id: str, buyer,
                       displayed_amount: Decimal,
                       displayed_currency: str,
                       charged_amount: Decimal,
                       charged_currency: str,
                       booked_fx_rate: Decimal,
                       expected_fx_rate: Decimal) -> CurrencyConversionDispute:
    diff = (Decimal(str(charged_amount)) -
            (Decimal(str(displayed_amount)) * Decimal(str(expected_fx_rate))))
    return CurrencyConversionDispute.objects.create(
        order_id=order_id[:64], buyer=buyer,
        displayed_amount=displayed_amount,
        displayed_currency=displayed_currency[:3],
        charged_amount=charged_amount,
        charged_currency=charged_currency[:3],
        booked_fx_rate=booked_fx_rate,
        expected_fx_rate=expected_fx_rate,
        difference=diff.quantize(Decimal('0.01')),
    )


def resolve_fx_dispute(dispute: CurrencyConversionDispute, *,
                          outcome: str,
                          notes: str = '') -> CurrencyConversionDispute:
    dispute.status = outcome
    dispute.resolution_notes = notes[:5000]
    dispute.decided_at = timezone.now()
    dispute.save(update_fields=['status', 'resolution_notes', 'decided_at'])
    return dispute


# ═══════════════════════════════════════════════════════════════════
# CH21 — Financial reporting
# ═══════════════════════════════════════════════════════════════════

def snapshot_financial_report(snapshot_date=None) -> FinancialReportSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)

    gmv = Decimal('0')
    refunds = Decimal('0')
    chargebacks_amt = Decimal('0')
    by_country = {}
    by_method = {}
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(created_at__gte=start, created_at__lt=end)
        gmv = Decimal(str(qs.aggregate(s=django_models.Sum('total_amount'))['s'] or 0))
    except Exception:
        pass
    try:
        from apps.payments.models import Refund
        refunds = Decimal(str(
            Refund.objects.filter(
                created_at__gte=start, created_at__lt=end,
            ).aggregate(s=django_models.Sum('amount'))['s'] or 0
        ))
    except Exception:
        pass
    try:
        from apps.payments.models import Chargeback
        chargebacks_amt = Decimal(str(
            Chargeback.objects.filter(
                created_at__gte=start, created_at__lt=end,
            ).aggregate(s=django_models.Sum('amount'))['s'] or 0
        ))
    except Exception:
        pass

    refund_rate = float(refunds / gmv) if gmv > 0 else 0.0
    chargeback_rate = float(chargebacks_amt / gmv) if gmv > 0 else 0.0
    # Commission proxy: 8% baseline.
    commission = (gmv * Decimal('0.08')).quantize(Decimal('0.01'))
    # COGS estimate proxy: 70% of GMV.
    cogs = (gmv * Decimal('0.70')).quantize(Decimal('0.01'))
    gross_profit = (gmv - cogs - refunds - chargebacks_amt).quantize(Decimal('0.01'))

    obj, _ = FinancialReportSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'gmv': gmv, 'net_revenue': gmv - refunds,
            'commission_revenue': commission,
            'refund_amount': refunds,
            'refund_rate': refund_rate,
            'chargeback_amount': chargebacks_amt,
            'chargeback_rate': chargeback_rate,
            'cogs_estimate': cogs,
            'gross_profit': gross_profit,
            'by_country': by_country, 'by_payment_method': by_method,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH22 — Sanctions screening
# ═══════════════════════════════════════════════════════════════════

# Minimal in-memory watchlist for dev. Production replaces with
# real OFAC + EU + UN feeds and a fuzzy matcher.
_INTERNAL_WATCHLIST = [
    {'name': 'evil corp', 'country': 'XX'},
    {'name': 'sanctioned individual', 'country': 'IR'},
]


def screen_for_sanctions(*, subject_user=None, name: str,
                            country: str = '',
                            context: str = 'checkout') -> SanctionsScreen | None:
    name_norm = name.strip().lower()
    name_hash = hashlib.sha256(name_norm.encode()).hexdigest()
    best_match = None
    best_conf = 0.0
    for entry in _INTERNAL_WATCHLIST:
        if entry['name'] in name_norm:
            conf = 0.9 if entry['name'] == name_norm else 0.7
            if conf > best_conf:
                best_match = entry
                best_conf = conf
    if best_conf < 0.6:
        return None
    obj = SanctionsScreen.objects.create(
        subject_user=subject_user, context=context,
        name_hash=name_hash, country=country[:2],
        list_source='internal',
        match_confidence=best_conf,
        match_details={'matched_entry': best_match},
        action_taken='blocked' if best_conf >= 0.85 else 'escalated',
    )
    PaymentOpsEvent.log(
        kind='sanctions.hit', user=subject_user,
        payload={'screen_id': obj.pk,
                 'confidence': best_conf,
                 'action': obj.action_taken},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH23 — Tokenisation register
# ═══════════════════════════════════════════════════════════════════

def register_tokenised_method(*, user, gateway: str,
                                 method_type: str,
                                 gateway_token: str,
                                 brand: str = '',
                                 last_four: str = '',
                                 expiry_month: int = None,
                                 expiry_year: int = None,
                                 three_ds_supported: bool = True) -> TokenisedPaymentMethod:
    fp = hashlib.sha256(gateway_token.encode()).hexdigest()
    # Dedup: same fingerprint → return existing row.
    existing = TokenisedPaymentMethod.objects.filter(
        user=user, fingerprint=fp,
    ).first()
    if existing:
        return existing
    return TokenisedPaymentMethod.objects.create(
        user=user, gateway=gateway[:24],
        method_type=method_type,
        brand=brand[:20], last_four=last_four[:4],
        expiry_month=expiry_month, expiry_year=expiry_year,
        gateway_token=gateway_token[:120],
        fingerprint=fp,
        three_ds_supported=three_ds_supported,
    )


def revoke_tokenised_method(method: TokenisedPaymentMethod) -> bool:
    if not method.is_active:
        return False
    method.is_active = False
    method.revoked_at = timezone.now()
    method.save(update_fields=['is_active', 'revoked_at'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_payment_ops_kpis(snapshot_date=None) -> PaymentOpsKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)
    # Transactions.
    tx_count = 0
    tx_value = Decimal('0')
    try:
        from apps.payment_gateways.models import PaymentIntent
        qs = PaymentIntent.objects.filter(created_at__gte=start, created_at__lt=end)
        tx_count = qs.count()
        tx_value = Decimal(str(qs.aggregate(s=django_models.Sum('amount'))['s'] or 0))
        succeeded = qs.filter(status='succeeded').count()
        failed = qs.filter(status='failed').count()
        auth_rate = (succeeded / tx_count * 100) if tx_count else 0
        fail_rate = (failed / tx_count * 100) if tx_count else 0
    except Exception:
        auth_rate = 0
        fail_rate = 0
    # Refund / chargeback rates.
    refund_amt = Decimal('0')
    chargeback_amt = Decimal('0')
    cb_count = 0
    cb_wins = 0
    try:
        from apps.payments.models import Refund, Chargeback
        refund_amt = Decimal(str(
            Refund.objects.filter(
                created_at__gte=start, created_at__lt=end,
            ).aggregate(s=django_models.Sum('amount'))['s'] or 0
        ))
        cb_qs = Chargeback.objects.filter(
            created_at__gte=start, created_at__lt=end,
        )
        cb_count = cb_qs.count()
        chargeback_amt = Decimal(str(
            cb_qs.aggregate(s=django_models.Sum('amount'))['s'] or 0
        ))
        cb_wins = ChargebackOutcome.objects.filter(
            chargeback_id__in=list(cb_qs.values_list('id', flat=True)),
            outcome__in=('won', 'partial_win'),
        ).count()
    except Exception:
        pass
    fx_pnl = (
        FxHedgePosition.objects.filter(
            settled_at__gte=start, settled_at__lt=end,
        ).aggregate(s=django_models.Sum('pnl'))['s'] or Decimal('0')
    )
    bnpl_defaults = BnplInstalmentPlan.objects.filter(
        status='defaulted',
    ).count()
    bnpl_total = BnplInstalmentPlan.objects.count() or 1
    bnpl_rate = bnpl_defaults / bnpl_total * 100
    wallet_topups = (
        WalletTopUp.objects.filter(
            completed_at__gte=start, completed_at__lt=end,
            status='succeeded',
        ).aggregate(s=django_models.Sum('amount'))['s'] or Decimal('0')
    )
    sanctions = SanctionsScreen.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end,
        action_taken='blocked',
    ).count()
    aml_open = AmlAlert.objects.filter(status='open').count()
    sar_filed = SarFiling.objects.filter(
        filed_at__gte=start, filed_at__lt=end,
    ).count()
    recon_open = ReconciliationException.objects.filter(resolved=False).count()
    b2b_overdue = (
        B2BInvoice.objects.filter(status='overdue').aggregate(
            s=django_models.Sum('amount'),
        )['s'] or Decimal('0')
    )
    by_gateway = {}
    try:
        from apps.payment_gateways.models import PaymentIntent
        for k, v in PaymentIntent.objects.values_list('gateway').annotate(
            c=django_models.Count('id'),
        ):
            by_gateway[k or ''] = v
    except Exception:
        pass

    obj, _ = PaymentOpsKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'transaction_count': tx_count,
            'transaction_value': tx_value,
            'auth_rate_pct': auth_rate,
            'failure_rate_pct': fail_rate,
            'chargeback_rate_pct': (chargeback_amt / tx_value * 100) if tx_value else 0,
            'chargeback_win_rate_pct': (cb_wins / cb_count * 100) if cb_count else 0,
            'refund_rate_pct': (refund_amt / tx_value * 100) if tx_value else 0,
            'fx_pnl': fx_pnl,
            'bnpl_default_rate_pct': bnpl_rate,
            'wallet_topups_total': wallet_topups,
            'sanctions_blocks': sanctions,
            'aml_alerts_open': aml_open,
            'sar_filings': sar_filed,
            'recon_exceptions_open': recon_open,
            'b2b_overdue_amount': b2b_overdue,
            'by_gateway': by_gateway,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# Recurring helpers (used by Celery)
# ═══════════════════════════════════════════════════════════════════

def mark_overdue_b2b() -> int:
    qs = B2BInvoice.objects.filter(
        status='issued', due_at__lt=timezone.now(),
    )
    now = timezone.now()
    n = 0
    for inv in qs.iterator():
        inv.status = 'overdue'
        inv.days_overdue = max(0, (now - inv.due_at).days)
        inv.save(update_fields=['status', 'days_overdue'])
        n += 1
    return n


def expire_store_credits() -> int:
    now = timezone.now()
    qs = StoreCredit.objects.filter(
        status='active', expires_at__lt=now,
    )
    return qs.update(status='expired')


def process_bnpl_late_payments() -> int:
    """Mark instalments as `late` after the due date passes."""
    qs = BnplInstalment.objects.filter(
        status='due', due_at__lt=timezone.now(),
    )
    return qs.update(status='late')
