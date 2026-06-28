"""
Accounting services — posting engine + master journal entry library +
financial statements.

The integrity backbone (doc CH1):
  1. Every journal: SUM(debits) == SUM(credits)  → else UnbalancedJournal
  2. Journals are immutable; corrections = reversal + correcting entry
  3. Closed periods reject new entries (period lock)
  4. All amounts integer AOA cents

Chapter → function map:
  CH1   seed_chart_of_accounts / period_of
  CH2   post_journal + master library (post_buyer_paid, post_delivery_
        confirmed, post_seller_payout, post_cod_*, post_psp_fee,
        post_wallet_*, post_refund, post_p2p)
  CH3/4/5/7  reconcile_sub_ledgers
  CH6   commission recognition (in post_delivery_confirmed)
  CH9   post_fx_revaluation
  CH11  calc_dispute_reserve
  CH12  post_iva_on_commission
  CH14  recognise_deferred_revenue
  CH19  amortise_capitalised
  CH20  age_receivables
  CH23  reverse_entry / correct_entry / lock_period
  CH24  trial_balance / profit_and_loss / balance_sheet /
        snapshot_financials
  CH10  month_end_close
"""
from datetime import date as _date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import chart_of_accounts as coa
from .models import (
    AccountingEvent, AccountingPeriod, AccountReceivable,
    CapitalisedDevelopment, DeferredRevenue, DisputeReserveLedger,
    EscrowLedger, FinancialStatementSnapshot, FxRevaluation, GLAccount,
    JournalEntry, JournalLine, SellerPayableLedger, SubLedgerReconciliation,
)

IVA_RATE_BPS = 1400  # 14% Angola IVA


class UnbalancedJournal(Exception):
    pass


class PeriodLocked(Exception):
    pass


# ──────────────────────────────────────────────────────────────────────
# CH1 — Setup helpers
# ──────────────────────────────────────────────────────────────────────

def seed_chart_of_accounts():
    """Idempotent: create any missing GL accounts from the chart."""
    created = 0
    for code, name, typ, nb in coa.CHART_OF_ACCOUNTS:
        _, was_created = GLAccount.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': typ, 'normal_balance': nb})
        created += 1 if was_created else 0
    return {'created': created, 'total': len(coa.CHART_OF_ACCOUNTS)}


def period_of(d):
    return d.strftime('%Y-%m')


def round_half_up_cents(value):
    return int(Decimal(str(value)).quantize(Decimal('1'),
                                            rounding=ROUND_HALF_UP))


def commission_cents(gross_cents, rate_bps):
    return round_half_up_cents(Decimal(gross_cents) * Decimal(rate_bps)
                               / Decimal(10000))


# ──────────────────────────────────────────────────────────────────────
# CH2 / CH23 — Posting engine
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def post_journal(*, entry_date, description, lines, source_type='system_auto',
                 source_id='', posted_by=None, approved_by=None, is_auto=True,
                 is_reversal=False, reversed_entry=None):
    """Post a balanced journal entry. `lines` is a list of dicts:
        {'account': '1000', 'debit': 4550000, 'description': '', 'party': u}
        {'account': '2000', 'credit': 4550000}
    Enforces debits==credits and an unlocked period.
    """
    period = period_of(entry_date)
    ap = AccountingPeriod.objects.filter(period=period).first()
    if ap and ap.is_locked:
        raise PeriodLocked(f'period {period} is closed')

    total_debit = sum(int(line.get('debit', 0)) for line in lines)
    total_credit = sum(int(line.get('credit', 0)) for line in lines)
    if total_debit != total_credit:
        raise UnbalancedJournal(
            f'debits {total_debit} != credits {total_credit}')
    if total_debit == 0:
        raise UnbalancedJournal('empty journal')

    entry = JournalEntry.objects.create(
        entry_date=entry_date, period=period, description=description[:300],
        source_type=source_type, source_id=str(source_id),
        posted_by=posted_by if getattr(posted_by, 'pk', None) else None,
        approved_by=approved_by if getattr(approved_by, 'pk', None) else None,
        is_auto=is_auto, is_reversal=is_reversal, reversed_entry=reversed_entry,
        total_cents=total_debit)

    account_cache = {}
    for line in lines:
        code = line['account']
        if code not in account_cache:
            account_cache[code] = GLAccount.objects.get(code=code)
        JournalLine.objects.create(
            entry=entry, account=account_cache[code],
            debit_cents=int(line.get('debit', 0)),
            credit_cents=int(line.get('credit', 0)),
            description=line.get('description', '')[:300],
            currency=line.get('currency', 'AOA'),
            party=line.get('party') if getattr(line.get('party'), 'pk', None)
            else None)
    return entry


def reverse_entry(original, *, posted_by=None, reason=''):
    """Create a mirror-image reversal (DR↔CR) preserving the original."""
    lines = []
    for ln in original.lines.all():
        lines.append({'account': ln.account_id,
                      'debit': ln.credit_cents, 'credit': ln.debit_cents,
                      'description': f'reversal: {ln.description}'[:300]})
    return post_journal(
        entry_date=timezone.now().date(),
        description=f'Reversal of {original.id}: {reason}'[:300],
        lines=lines, source_type='reversal', source_id=str(original.id),
        posted_by=posted_by, is_auto=False, is_reversal=True,
        reversed_entry=original)


# ──────────────────────────────────────────────────────────────────────
# CH2 — Master journal entry library
# ──────────────────────────────────────────────────────────────────────

def post_buyer_paid(*, order_id, gross_cents, seller=None,
                    cash_account='1020', method='mcx_reference',
                    entry_date=None):
    """EVENT 1: buyer pays (prepaid). DR Cash, CR Escrow. Creates escrow
    sub-ledger row (doc CH2/CH3). Idempotent per order.
    """
    if EscrowLedger.objects.filter(order_id=order_id).exists():
        return EscrowLedger.objects.get(order_id=order_id)
    entry_date = entry_date or timezone.now().date()
    post_journal(
        entry_date=entry_date,
        description=f'Buyer paid order {order_id}',
        lines=[{'account': cash_account, 'debit': gross_cents},
               {'account': '2000', 'credit': gross_cents}],
        source_type='system_auto', source_id=order_id)
    el = EscrowLedger.objects.create(
        order_id=order_id, seller=seller, gross_amount_cents=gross_cents,
        status='held', payment_method=method,
        funds_received_at=timezone.now())
    AccountingEvent.log('buyer_paid', order_id=order_id, gross=gross_cents)
    return el


@transaction.atomic
def post_delivery_confirmed(*, order_id, rate_bps=600, release_trigger='auto',
                            entry_date=None):
    """EVENT 2: delivery confirmed → recognise revenue (IFRS 15). Escrow
    release: DR Escrow, CR Commission Revenue, CR Seller Payable.
    """
    el = EscrowLedger.objects.select_for_update().get(order_id=order_id)
    if el.status == 'released':
        return el
    entry_date = entry_date or timezone.now().date()
    comm = commission_cents(el.gross_amount_cents, rate_bps)
    net = el.gross_amount_cents - comm
    post_journal(
        entry_date=entry_date,
        description=f'Escrow release order {order_id} (delivery confirmed)',
        lines=[{'account': '2000', 'debit': el.gross_amount_cents},
               {'account': '4000', 'credit': comm,
                'description': 'commission revenue'},
               {'account': '2020', 'credit': net, 'party': el.seller,
                'description': 'seller payable'}],
        source_type='system_auto', source_id=order_id)
    el.commission_cents = comm
    el.net_seller_cents = net
    el.status = 'released'
    el.release_trigger = release_trigger
    el.released_at = timezone.now()
    el.save()
    SellerPayableLedger.objects.create(
        seller=el.seller, order_id=order_id,
        gross_cents=el.gross_amount_cents, commission_cents=comm,
        net_cents=net, status='accrued')
    AccountingEvent.log('delivery_confirmed', order_id=order_id,
                        commission=comm, net=net)
    return el


@transaction.atomic
def post_seller_payout(*, seller, batch_id, entry_date=None):
    """EVENT 3: weekly payout batch. Aggregate accrued payable → DR 2020
    CR 1000 (doc CH5). Excludes disputed rows.
    """
    entry_date = entry_date or timezone.now().date()
    rows = list(SellerPayableLedger.objects.select_for_update().filter(
        seller=seller, status='accrued'))
    if not rows:
        return {'paid_cents': 0, 'rows': 0}
    total = sum(r.net_cents + r.adjustments_cents for r in rows)
    if total <= 0:
        return {'paid_cents': 0, 'rows': 0}
    post_journal(
        entry_date=entry_date,
        description=f'Seller payout batch {batch_id} → seller {seller.pk}',
        lines=[{'account': '2020', 'debit': total, 'party': seller},
               {'account': '1000', 'credit': total}],
        source_type='system_auto', source_id=batch_id)
    for r in rows:
        r.status = 'paid'
        r.payout_batch_id = batch_id
        r.paid_at = timezone.now()
        r.save(update_fields=['status', 'payout_batch_id', 'paid_at'])
    AccountingEvent.log('seller_payout', seller_id=seller.pk,
                        batch=batch_id, paid=total)
    return {'paid_cents': total, 'rows': len(rows)}


def post_psp_fee(*, order_id, gross_cents, fee_cents, entry_date=None):
    """EVENT 7: APPYPAY fee. DR 5000 fee, DR 1000 net, CR 1020 gross."""
    entry_date = entry_date or timezone.now().date()
    net = gross_cents - fee_cents
    return post_journal(
        entry_date=entry_date,
        description=f'PSP settlement order {order_id}',
        lines=[{'account': '5000', 'debit': fee_cents},
               {'account': '1000', 'debit': net},
               {'account': '1020', 'credit': gross_cents}],
        source_type='system_auto', source_id=order_id)


def post_wallet_topup(*, user, amount_cents, cash_account='1020',
                      entry_date=None):
    """EVENT 8: DR Cash, CR Wallet Liability."""
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'Wallet top-up user {user.pk}',
        lines=[{'account': cash_account, 'debit': amount_cents},
               {'account': '2010', 'credit': amount_cents, 'party': user}],
        source_type='system_auto', source_id=f'topup:{user.pk}')


def post_wallet_spend(*, user, order_id, amount_cents, seller=None,
                      entry_date=None):
    """EVENT 9: DR Wallet Liability, CR Escrow. Creates the escrow
    sub-ledger row so GL 2000 stays reconciled (doc CH9 → escrow → revenue).
    """
    entry = post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'Wallet spend order {order_id}',
        lines=[{'account': '2010', 'debit': amount_cents, 'party': user},
               {'account': '2000', 'credit': amount_cents}],
        source_type='system_auto', source_id=order_id)
    EscrowLedger.objects.get_or_create(
        order_id=order_id,
        defaults={'seller': seller, 'gross_amount_cents': amount_cents,
                  'status': 'held', 'payment_method': 'wallet',
                  'funds_received_at': timezone.now()})
    return entry


def post_p2p(*, sender, recipient, amount_cents, transfer_id, entry_date=None):
    """EVENT 12: liability reallocation. DR Wallet(sender) CR Wallet(recip)."""
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'P2P transfer {transfer_id}',
        lines=[{'account': '2010', 'debit': amount_cents, 'party': sender,
                'description': 'sender'},
               {'account': '2010', 'credit': amount_cents, 'party': recipient,
                'description': 'recipient'}],
        source_type='system_auto', source_id=str(transfer_id))


# ── COD cycle (CH16) ──────────────────────────────────────────────────

def post_cod_collected(*, order_id, amount_cents, entry_date=None):
    """DR 1030 Cash in Transit, CR 2060 COD Clearing."""
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'COD collected order {order_id}',
        lines=[{'account': '1030', 'debit': amount_cents},
               {'account': '2060', 'credit': amount_cents}],
        source_type='system_auto', source_id=order_id)


def post_cod_remitted(*, order_id, amount_cents, entry_date=None):
    """DR 1000 Cash — BAI, CR 1030 Cash in Transit."""
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'COD remitted order {order_id}',
        lines=[{'account': '1000', 'debit': amount_cents},
               {'account': '1030', 'credit': amount_cents}],
        source_type='system_auto', source_id=order_id)


def post_cod_reconciled(*, order_id, amount_cents, seller=None, rate_bps=600,
                        entry_date=None):
    """DR 2060 COD Clearing, CR 4000 Commission, CR 2020 Seller Payable."""
    comm = commission_cents(amount_cents, rate_bps)
    net = amount_cents - comm
    entry = post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'COD reconciled order {order_id}',
        lines=[{'account': '2060', 'debit': amount_cents},
               {'account': '4000', 'credit': comm},
               {'account': '2020', 'credit': net, 'party': seller}],
        source_type='system_auto', source_id=order_id)
    SellerPayableLedger.objects.create(
        seller=seller, order_id=order_id, gross_cents=amount_cents,
        commission_cents=comm, net_cents=net, status='accrued')
    return entry


def post_courier_shortfall(*, courier, order_id, deposited_cents,
                           expected_cents, entry_date=None):
    """Courier deposits less than collected (doc CH16). DR 1000 deposited,
    DR 1101 AR-courier shortfall, CR 1030.
    """
    short = expected_cents - deposited_cents
    entry = post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'COD shortfall order {order_id}',
        lines=[{'account': '1000', 'debit': deposited_cents},
               {'account': '1101', 'debit': short, 'party': courier},
               {'account': '1030', 'credit': expected_cents}],
        source_type='system_auto', source_id=order_id)
    AccountReceivable.objects.create(
        debtor=courier, kind='courier_shortfall', amount_cents=short,
        account_code='1101', raised_at=timezone.now().date(),
        note=f'COD shortfall order {order_id}')
    return entry


# ── Refunds & chargebacks (CH8) ───────────────────────────────────────

@transaction.atomic
def post_refund(*, order_id, amount_cents, target='wallet', user=None,
                escrow_released=None, seller=None, entry_date=None):
    """Refund routing (doc CH8). Before release: DR Escrow. After release
    (seller not yet paid): DR Seller Payable. Credit wallet or refunds payable.
    """
    entry_date = entry_date or timezone.now().date()
    el = EscrowLedger.objects.select_for_update().filter(
        order_id=order_id).first()
    if escrow_released is None:
        escrow_released = bool(el and el.status == 'released')
    credit_code = '2010' if target == 'wallet' else '2040'
    debit_code = '2020' if escrow_released else '2000'
    entry = post_journal(
        entry_date=entry_date,
        description=f'Refund order {order_id} ({target})',
        lines=[{'account': debit_code, 'debit': amount_cents,
                'party': seller if escrow_released else None},
               {'account': credit_code, 'credit': amount_cents,
                'party': user if target == 'wallet' else None}],
        source_type='system_auto', source_id=order_id)
    if el:
        el.refunded_cents += amount_cents
        el.status = ('clawed_back' if el.refunded_cents >= el.gross_amount_cents
                     else 'partially_clawed')
        el.save(update_fields=['refunded_cents', 'status'])
    AccountingEvent.log('refund', order_id=order_id, amount=amount_cents,
                        target=target, escrow_released=escrow_released)
    return entry


def post_chargeback(*, order_id, amount_cents, seller=None,
                    escrow_released=True, entry_date=None):
    """Chargeback notification (doc CH8). DR Seller Payable/Escrow, CR Cash."""
    debit_code = '2020' if escrow_released else '2000'
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'Chargeback order {order_id}',
        lines=[{'account': debit_code, 'debit': amount_cents, 'party': seller},
               {'account': '1000', 'credit': amount_cents}],
        source_type='system_auto', source_id=order_id)


# ── Promo voucher (CH15) ──────────────────────────────────────────────

def post_platform_voucher(*, order_id, buyer_paid_cents, subsidy_cents,
                          entry_date=None):
    """TYPE A platform-funded voucher (doc CH15). DR Cash (buyer paid),
    DR Marketing (subsidy), CR Escrow (full GMV).
    """
    gmv = buyer_paid_cents + subsidy_cents
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'Platform voucher order {order_id}',
        lines=[{'account': '1020', 'debit': buyer_paid_cents},
               {'account': '6020', 'debit': subsidy_cents,
                'description': 'voucher subsidy'},
               {'account': '2000', 'credit': gmv}],
        source_type='system_auto', source_id=order_id)


# ── IVA (CH12) ────────────────────────────────────────────────────────

def post_iva_on_commission(*, order_id, commission_cents_, entry_date=None):
    """IVA exclusive (on top, doc CH12). The extra IVA portion comes out of
    escrow (buyer paid it on top): DR Escrow (IVA), CR IVA Payable.
    """
    iva = round_half_up_cents(Decimal(commission_cents_) * IVA_RATE_BPS / 10000)
    return post_journal(
        entry_date=entry_date or timezone.now().date(),
        description=f'IVA on commission order {order_id}',
        lines=[{'account': '2000', 'debit': iva, 'description': 'IVA portion'},
               {'account': '2030', 'credit': iva}],
        source_type='system_auto', source_id=f'iva:{order_id}')


# ──────────────────────────────────────────────────────────────────────
# Account balances + statements (CH24)
# ──────────────────────────────────────────────────────────────────────

def raw_balance(code, *, as_of=None):
    """Net = SUM(debit) - SUM(credit). Positive = net debit."""
    qs = JournalLine.objects.filter(account_id=code)
    if as_of:
        qs = qs.filter(entry__entry_date__lte=as_of)
    agg = qs.aggregate(d=Sum('debit_cents'), c=Sum('credit_cents'))
    return int(agg['d'] or 0) - int(agg['c'] or 0)


def account_balance(code, *, as_of=None):
    """Balance in the account's natural sign (positive = its normal side)."""
    raw = raw_balance(code, as_of=as_of)
    return raw if coa.NORMAL_BALANCE.get(code) == coa.DEBIT else -raw


def trial_balance(*, as_of=None):
    """Returns {balanced, total_debit, total_credit, rows}. Balanced when
    total debits == total credits (the integrity proof, doc CH24 D1).
    """
    rows = []
    total_d = total_c = 0
    for acc in GLAccount.objects.all():
        agg = JournalLine.objects.filter(account=acc)
        if as_of:
            agg = agg.filter(entry__entry_date__lte=as_of)
        agg = agg.aggregate(d=Sum('debit_cents'), c=Sum('credit_cents'))
        d, c = int(agg['d'] or 0), int(agg['c'] or 0)
        net = d - c
        if net == 0 and d == 0:
            continue
        rows.append({'code': acc.code, 'name': acc.name,
                     'debit': net if net > 0 else 0,
                     'credit': -net if net < 0 else 0})
        total_d += net if net > 0 else 0
        total_c += -net if net < 0 else 0
    return {'balanced': total_d == total_c, 'total_debit': total_d,
            'total_credit': total_c, 'rows': rows}


def _category_raw(codes, sign, *, period=None, as_of=None):
    """Category total = sign × SUM(raw_balance) over codes.

    Uses RAW (debit−credit) with a single CATEGORY sign — not each
    account's own normal balance. This is what makes contra accounts
    (1150 Allowance, 1450 Accumulated Amortisation — credit-balance rows
    inside the asset category) net DOWN the category total correctly, and
    guarantees the balance sheet ties to the trial balance exactly.
    """
    raw = 0
    qs = JournalLine.objects.filter(account_id__in=list(codes))
    if period:
        qs = qs.filter(entry__period=period)
    if as_of:
        qs = qs.filter(entry__entry_date__lte=as_of)
    agg = qs.aggregate(d=Sum('debit_cents'), c=Sum('credit_cents'))
    raw = int(agg['d'] or 0) - int(agg['c'] or 0)
    return sign * raw


def profit_and_loss(period):
    """P&L for a period (doc CH24). All values in cents."""
    revenue = _category_raw(coa.REVENUE_CODES, -1, period=period)
    cor = _category_raw(coa.COR_CODES, +1, period=period)
    gross_profit = revenue - cor
    opex = _category_raw(coa.OPEX_CODES, +1, period=period)
    ebitda = gross_profit - opex
    other = _category_raw(coa.OTHER_CODES, -1, period=period)  # net income
    pbt = ebitda + other
    tax = _category_raw(['6500'], +1, period=period)
    net_profit = pbt - tax
    commission = _category_raw(['4000'], -1, period=period)
    return {'revenue': revenue, 'cost_of_revenue': cor,
            'gross_profit': gross_profit, 'opex': opex, 'ebitda': ebitda,
            'other': other, 'pbt': pbt, 'income_tax': tax,
            'net_profit': net_profit,
            'take_rate_pct': round(commission / revenue * 100, 2)
            if revenue else 0,
            'gross_margin_pct': round(gross_profit / revenue * 100, 2)
            if revenue else 0}


def balance_sheet(*, as_of=None):
    """Balance sheet (doc CH24). Assets == Liabilities + Equity — ties to
    the trial balance exactly because it regroups the same raw balances.
    """
    assets = _category_raw(coa.ASSET_CODES, +1, as_of=as_of)
    liabilities = _category_raw(coa.LIABILITY_CODES, -1, as_of=as_of)
    equity = _category_raw(coa.EQUITY_CODES, -1, as_of=as_of)
    # Retained earnings = net P&L to date (no dedicated posting account).
    revenue = _category_raw(coa.REVENUE_CODES, -1, as_of=as_of)
    expenses = _category_raw(coa.COR_CODES + coa.OPEX_CODES + ['6500'], +1,
                             as_of=as_of)
    other = _category_raw(coa.OTHER_CODES, -1, as_of=as_of)
    retained = revenue - expenses + other
    equity_total = equity + retained
    return {'assets': assets, 'liabilities': liabilities,
            'equity': equity_total, 'retained_earnings': retained,
            'balanced': assets == liabilities + equity_total}


# ──────────────────────────────────────────────────────────────────────
# CH3/4/5 — Sub-ledger reconciliation
# ──────────────────────────────────────────────────────────────────────

def reconcile_sub_ledgers(recon_date=None):
    """Escrow / seller-payable sub-ledgers vs their GL parent accounts."""
    recon_date = recon_date or timezone.now().date()
    results = []

    escrow_sub = EscrowLedger.objects.filter(
        status__in=('held', 'releasable')).aggregate(
        s=Sum('gross_amount_cents'))['s'] or 0
    results.append(_record_recon(recon_date, 'escrow', '2000', escrow_sub))

    payable_sub = SellerPayableLedger.objects.filter(
        status__in=('accrued', 'adjusting')).aggregate(
        s=Sum('net_cents'))['s'] or 0
    results.append(_record_recon(recon_date, 'seller_payable', '2020',
                                 payable_sub))
    return results


def _record_recon(recon_date, ledger, gl_code, sub_total):
    gl_bal = account_balance(gl_code)
    diff = sub_total - gl_bal
    rec, _ = SubLedgerReconciliation.objects.update_or_create(
        recon_date=recon_date, ledger=ledger,
        defaults={'gl_account_code': gl_code,
                  'sub_ledger_total_cents': sub_total,
                  'gl_balance_cents': gl_bal, 'difference_cents': diff,
                  'balanced': diff == 0})
    if diff != 0:
        AccountingEvent.log('subledger_mismatch', ledger=ledger,
                            difference=diff)
    return rec


# ──────────────────────────────────────────────────────────────────────
# CH11 — Dispute reserve
# ──────────────────────────────────────────────────────────────────────

def calc_dispute_reserve(*, open_dispute_value_cents, p_full=0.25,
                         p_partial=0.15, snapshot_date=None, posted_by=None):
    """Adjust the dispute reserve (2050) to expected loss (doc CH11)."""
    snapshot_date = snapshot_date or timezone.now().date()
    expected = round_half_up_cents(
        Decimal(open_dispute_value_cents) * Decimal(str(p_full))
        + Decimal(open_dispute_value_cents) * Decimal(str(p_partial))
        * Decimal('0.5'))
    prior = account_balance('2050')
    adjustment = expected - prior
    entry = None
    if adjustment > 0:
        entry = post_journal(
            entry_date=snapshot_date,
            description='Dispute reserve increase',
            lines=[{'account': '5020', 'debit': adjustment},
                   {'account': '2050', 'credit': adjustment}],
            source_type='accrual', source_id=f'reserve:{snapshot_date}')
    elif adjustment < 0:
        entry = post_journal(
            entry_date=snapshot_date,
            description='Dispute reserve release',
            lines=[{'account': '2050', 'debit': -adjustment},
                   {'account': '4990', 'credit': -adjustment}],
            source_type='accrual', source_id=f'reserve:{snapshot_date}')
    DisputeReserveLedger.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={'open_dispute_value_cents': open_dispute_value_cents,
                  'expected_loss_cents': expected, 'prior_reserve_cents': prior,
                  'adjustment_cents': adjustment, 'journal_entry': entry})
    return {'expected': expected, 'prior': prior, 'adjustment': adjustment}


# ──────────────────────────────────────────────────────────────────────
# CH14 — Deferred revenue recognition
# ──────────────────────────────────────────────────────────────────────

def recognise_deferred_revenue(recognise_date=None):
    """Monthly straight-line recognition of deferred annual fees (CH14)."""
    recognise_date = recognise_date or timezone.now().date()
    recognised = 0
    for dr in DeferredRevenue.objects.filter(is_active=True):
        if dr.months_recognised >= dr.months_total:
            dr.is_active = False
            dr.save(update_fields=['is_active'])
            continue
        monthly = dr.total_cents // dr.months_total
        # last month picks up the rounding remainder
        if dr.months_recognised == dr.months_total - 1:
            monthly = dr.total_cents - dr.recognised_cents
        post_journal(
            entry_date=recognise_date,
            description=f'Recognise {dr.get_kind_display()} seller {dr.seller_id}',
            lines=[{'account': '2100', 'debit': monthly},
                   {'account': dr.revenue_account_code, 'credit': monthly,
                    'party': dr.seller}],
            source_type='system_auto', source_id=f'deferred:{dr.id}')
        dr.recognised_cents += monthly
        dr.months_recognised += 1
        if dr.months_recognised >= dr.months_total:
            dr.is_active = False
        dr.save()
        recognised += 1
    return {'recognised': recognised}


# ──────────────────────────────────────────────────────────────────────
# CH19 — Amortisation of capitalised development
# ──────────────────────────────────────────────────────────────────────

def amortise_capitalised(amort_date=None):
    """Monthly straight-line amortisation of live capitalised features."""
    amort_date = amort_date or timezone.now().date()
    amortised = 0
    for cap in CapitalisedDevelopment.objects.filter(status='live'):
        monthly = cap.capitalised_cents // cap.useful_life_months
        remaining = cap.net_book_value_cents
        monthly = min(monthly, remaining)
        if monthly <= 0:
            cap.status = 'fully_amortised'
            cap.save(update_fields=['status'])
            continue
        post_journal(
            entry_date=amort_date,
            description=f'Amortise {cap.feature_name}',
            lines=[{'account': '6011', 'debit': monthly},
                   {'account': '1450', 'credit': monthly}],
            source_type='system_auto', source_id=f'amort:{cap.id}')
        cap.amortised_cents += monthly
        if cap.net_book_value_cents <= 0:
            cap.status = 'fully_amortised'
        cap.save()
        amortised += 1
    return {'amortised': amortised}


# ──────────────────────────────────────────────────────────────────────
# CH9 — FX revaluation
# ──────────────────────────────────────────────────────────────────────

def post_fx_revaluation(*, currency, foreign_amount, opening_rate,
                        closing_rate, snapshot_date=None):
    """Month-end FX revaluation (doc CH9). Posts unrealised gain/loss."""
    snapshot_date = snapshot_date or timezone.now().date()
    diff = (Decimal(str(foreign_amount))
            * (Decimal(str(closing_rate)) - Decimal(str(opening_rate))))
    gain_loss_cents = round_half_up_cents(diff * 100)
    entry = None
    if gain_loss_cents > 0:
        entry = post_journal(
            entry_date=snapshot_date,
            description=f'FX revaluation gain {currency}',
            lines=[{'account': '2099', 'debit': gain_loss_cents},
                   {'account': '7000', 'credit': gain_loss_cents}],
            source_type='accrual', source_id=f'fx:{currency}:{snapshot_date}')
    elif gain_loss_cents < 0:
        entry = post_journal(
            entry_date=snapshot_date,
            description=f'FX revaluation loss {currency}',
            lines=[{'account': '7000', 'debit': -gain_loss_cents},
                   {'account': '2099', 'credit': -gain_loss_cents}],
            source_type='accrual', source_id=f'fx:{currency}:{snapshot_date}')
    FxRevaluation.objects.create(
        snapshot_date=snapshot_date, currency=currency,
        foreign_amount=Decimal(str(foreign_amount)),
        opening_rate=Decimal(str(opening_rate)),
        closing_rate=Decimal(str(closing_rate)),
        gain_loss_cents=gain_loss_cents, journal_entry=entry)
    return gain_loss_cents


# ──────────────────────────────────────────────────────────────────────
# CH20 — AR ageing
# ──────────────────────────────────────────────────────────────────────

def age_receivables(as_of=None):
    """Bucket open receivables by age (doc CH20)."""
    as_of = as_of or timezone.now().date()
    buckets = {'current': 0, 'watch': 0, 'doubtful': 0, 'overdue': 0}
    for ar in AccountReceivable.objects.filter(
            status__in=('open', 'partially_recovered')):
        age = (as_of - ar.raised_at).days
        amt = ar.outstanding_cents
        if age <= 30:
            buckets['current'] += amt
        elif age <= 60:
            buckets['watch'] += amt
        elif age <= 90:
            buckets['doubtful'] += amt
        else:
            buckets['overdue'] += amt
    return buckets


# ──────────────────────────────────────────────────────────────────────
# CH23 / CH10 — Period lock + month-end close
# ──────────────────────────────────────────────────────────────────────

def lock_period(period, *, locked_by=None):
    ap, _ = AccountingPeriod.objects.get_or_create(period=period)
    ap.is_locked = True
    ap.locked_by = locked_by if getattr(locked_by, 'pk', None) else None
    ap.locked_at = timezone.now()
    ap.save()
    AccountingEvent.log('period_locked', actor=locked_by, period=period)
    return ap


def unlock_period(period, *, by=None, reason=''):
    ap = AccountingPeriod.objects.filter(period=period).first()
    if ap:
        ap.is_locked = False
        ap.unlocked_reason = reason[:300]
        ap.save(update_fields=['is_locked', 'unlocked_reason'])
        AccountingEvent.log('period_unlocked', actor=by, period=period,
                            reason=reason)
    return ap


def month_end_close(period, *, by=None, lock=True):
    """Run reconciliations + statement snapshot, then lock (doc CH10)."""
    recons = reconcile_sub_ledgers()
    tb = trial_balance()
    snap = snapshot_financials(period)
    locked = lock_period(period, locked_by=by) if lock else None
    return {'trial_balance_balanced': tb['balanced'],
            'reconciliations': [(r.ledger, r.balanced) for r in recons],
            'net_profit_cents': snap.net_profit_cents,
            'locked': bool(locked)}


# ──────────────────────────────────────────────────────────────────────
# CH24 — Statement snapshot
# ──────────────────────────────────────────────────────────────────────

def snapshot_financials(period):
    pnl = profit_and_loss(period)
    # Balance sheet as of period end (last day) — approximate with as_of None
    # restricted by period upper bound.
    year, month = (int(x) for x in period.split('-'))
    end = (_date(year + 1, 1, 1) if month == 12
           else _date(year, month + 1, 1))
    bs = balance_sheet(as_of=end)
    tb = trial_balance()
    snap, _ = FinancialStatementSnapshot.objects.update_or_create(
        period=period,
        defaults={
            'total_revenue_cents': pnl['revenue'],
            'total_cor_cents': pnl['cost_of_revenue'],
            'gross_profit_cents': pnl['gross_profit'],
            'total_opex_cents': pnl['opex'],
            'ebitda_cents': pnl['ebitda'],
            'other_income_cents': pnl['other'],
            'pbt_cents': pnl['pbt'],
            'income_tax_cents': pnl['income_tax'],
            'net_profit_cents': pnl['net_profit'],
            'total_assets_cents': bs['assets'],
            'total_liabilities_cents': bs['liabilities'],
            'total_equity_cents': bs['equity'],
            'balance_sheet_balanced': bs['balanced'],
            'trial_balance_balanced': tb['balanced'],
            'take_rate_pct': pnl['take_rate_pct'],
            'gross_margin_pct': pnl['gross_margin_pct'],
            'detail': {'pnl': pnl, 'balance_sheet': bs},
        })
    return snap
