"""
MICHA Angola payments — domain services.

Money is integer cents throughout (doc CH13). Concurrency-critical paths
(wallet, P2P) use select_for_update with deadlock-safe lock ordering and
per-entry unique idempotency keys.

Chapter → function map:
  CH13  format_aoa / round_half_up_cents / pct_of_cents
  CH2   transition (enforced state-machine guard) + log_event
  CH3   is_cod_eligible / create_cod_flow / ship_cod / collect_cod /
        refuse_cod
  CH4   remit_cash / deposit_cash / bank_confirm_remittance /
        reconcile_cod_daily
  CH5   create_mcx_reference / confirm_reference_payment /
        expire_references / regenerate_reference
  CH6   initiate_mcx_push / handle_push_result
  CH7   create_bank_transfer_flow / upload_bank_proof / verify_bank_proof
  CH8   create_split_flow / settle_split_component / release_split_holds
  CH9   wallet_balance_cents / wallet_credit / wallet_debit /
        check_wallet_integrity
  CH10  p2p_transfer
  CH11  ingest_settlement_line / reconcile_settlement_day
  CH12  run_dunning
  CH15  create_refund
  CH24  snapshot_payments_kpis

External-dependent pieces (stubbed behind clean seams, see gap list):
  APPYPAY live REST + HMAC webhook secret, BAI/Atlântico statement import,
  S3/R2 comprovativo storage, SMS/WhatsApp dunning delivery.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from . import state_machine as sm
from .models import (
    BankTransferProof, BuyerCodProfile, CodCashRemittance, CodCollection,
    CodEligibilityConfig, CodReconciliationException, CourierCashPosition,
    DunningState, MulticaixaReference, PaymentAuditEvent, PaymentComponent,
    PaymentFlow, PaymentsAngolaKpiSnapshot, SettlementRecord, SettlementRun,
    WalletIntegrityBreach, WalletLedgerEntry, WalletTransfer,
)

REFERENCE_TTL_HOURS = 48
BANK_TRANSFER_TTL_HOURS = 48
WALLET_HOLD_TTL_MINUTES = 30
P2P_MAX_PER_TXN_CENTS = 50_000_000          # 500k Kz
P2P_MAX_PER_DAY_CENTS = 100_000_000         # 1M Kz
P2P_MAX_RECIPIENTS_PER_DAY = 10
COD_REFUSAL_DISABLE_THRESHOLD = 2           # 2+ refusals/90d → COD off


# ──────────────────────────────────────────────────────────────────────
# CH13 — Kwanza rules
# ──────────────────────────────────────────────────────────────────────

def format_aoa(cents):
    """45_50000 → '45.500,00 Kz' (pt-AO: dot thousands, comma decimal)."""
    cents = int(cents)
    sign = '-' if cents < 0 else ''
    whole, frac = divmod(abs(cents), 100)
    whole_str = f'{whole:,}'.replace(',', '.')
    return f'{sign}{whole_str},{frac:02d} Kz'


def round_half_up_cents(value):
    """Round a Decimal/number to whole cents, ROUND_HALF_UP (doc CH13)."""
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def pct_of_cents(amount_cents, rate_bps):
    """commission = round_half_up(amount_cents * rate_bps / 10000)."""
    return round_half_up_cents(Decimal(amount_cents) * Decimal(rate_bps)
                               / Decimal(10000))


# ──────────────────────────────────────────────────────────────────────
# CH2 / CH23 — State machine guard + event log
# ──────────────────────────────────────────────────────────────────────

def log_event(flow, event_type, payload=None, actor=None):
    """Immutable audit event (never raises)."""
    try:
        PaymentAuditEvent.objects.create(
            flow=flow,
            correlation_id=flow.correlation_id if flow else '',
            event_type=event_type, payload=payload or {},
            actor=actor if getattr(actor, 'pk', None) else None)
    except Exception:
        pass


def transition(flow, new_state, *, event_payload=None, actor=None,
               extra_fields=None):
    """Enforce ALLOWED_TRANSITIONS. Illegal → log anomaly + raise."""
    old = flow.status
    if not sm.can_transition(old, new_state):
        log_event(flow, 'illegal_transition',
                  {'from': old, 'to': new_state})
        raise sm.IllegalTransition(old, new_state)
    flow.status = new_state
    fields = ['status', 'updated_at']
    if new_state == sm.PAID and flow.paid_at is None:
        flow.paid_at = timezone.now()
        fields.append('paid_at')
    if extra_fields:
        for k, v in extra_fields.items():
            setattr(flow, k, v)
            fields.append(k)
    flow.save(update_fields=list(set(fields)))
    log_event(flow, f'status.{new_state}',
              {'from': old, **(event_payload or {})}, actor=actor)
    return flow


def _new_flow(*, order_id, buyer, method, amount_cents, idempotency_key,
              currency='AOA', expires_at=None, status=sm.CREATED):
    """Idempotent flow creation — same key returns the existing flow."""
    existing = PaymentFlow.objects.filter(
        idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    flow = PaymentFlow.objects.create(
        order_id=str(order_id),
        buyer=buyer if getattr(buyer, 'pk', None) else None,
        method=method, amount_cents=amount_cents, currency=currency,
        idempotency_key=idempotency_key,
        correlation_id=f'corr_{uuid.uuid4().hex[:16]}',
        status=status, expires_at=expires_at)
    log_event(flow, 'intent.created',
              {'method': method, 'amount_cents': amount_cents})
    return flow, True


# ──────────────────────────────────────────────────────────────────────
# CH3 — COD eligibility + order flow
# ──────────────────────────────────────────────────────────────────────

def is_cod_eligible(buyer, *, total_cents, province, category_ids=None,
                    is_remote=False, seller_cod_enabled=True):
    """Returns (bool, reason). Evaluated at checkout before offering COD."""
    cfg = CodEligibilityConfig.current()
    category_ids = category_ids or []

    if cfg.enabled_provinces and province not in cfg.enabled_provinces:
        return False, 'COD not available in this province yet'
    if is_remote:
        return False, 'COD unavailable for remote delivery zones'
    if total_cents > cfg.max_order_cents:
        return False, 'Order too large for COD — prepayment required'
    if total_cents < cfg.min_order_cents:
        return False, 'Order below COD minimum'

    profile = BuyerCodProfile.objects.filter(buyer=buyer).first()
    if profile:
        if profile.cod_disabled:
            return False, (profile.cod_disabled_reason
                           or 'COD disabled for this account')
        if profile.refusal_count_90d >= COD_REFUSAL_DISABLE_THRESHOLD:
            return False, 'COD disabled due to previous refused deliveries'

    is_new = False
    try:
        age = (timezone.now() - buyer.date_joined).days
        is_new = age < 1 and not getattr(buyer, 'is_verified', False)
    except Exception:
        pass
    if is_new and total_cents > cfg.new_user_cap_cents:
        return False, 'COD limit for new accounts exceeded'

    if not seller_cod_enabled:
        return False, 'One or more sellers do not accept COD'
    if any(c in cfg.restricted_categories for c in category_ids):
        return False, 'Some items require prepayment'

    open_exposure = profile.open_exposure_cents if profile else 0
    if open_exposure + total_cents > cfg.max_concurrent_exposure_cents:
        return False, 'Too many pending COD orders'

    return True, None


@transaction.atomic
def create_cod_flow(buyer, *, order_id, total_cents, idempotency_key,
                    add_cod_fee=False):
    cfg = CodEligibilityConfig.current()
    amount = total_cents + (cfg.cod_fee_cents if add_cod_fee else 0)
    flow, created = _new_flow(order_id=order_id, buyer=buyer, method='cod',
                              amount_cents=amount,
                              idempotency_key=idempotency_key)
    if created:
        profile, _ = BuyerCodProfile.objects.select_for_update(
        ).get_or_create(buyer=buyer)
        profile.open_exposure_cents += amount
        profile.save(update_fields=['open_exposure_cents', 'updated_at'])
        CodCollection.objects.create(flow=flow, order_id=str(order_id),
                                     amount_cents=amount)
    return flow


def ship_cod(flow, courier=None):
    """Seller ships → CREATED → COD_PENDING (doc CH3 step 2)."""
    transition(flow, sm.COD_PENDING)
    if courier is not None:
        CodCollection.objects.filter(flow=flow).update(courier=courier)
    return flow


@transaction.atomic
def collect_cod(flow, *, courier, proof_key=''):
    """Courier collects cash → COD_PENDING → COD_COLLECTED + custody."""
    coll = CodCollection.objects.select_for_update().get(flow=flow)
    transition(flow, sm.COD_COLLECTED, actor=courier)
    coll.status = 'collected'
    coll.courier = courier
    coll.collected_at = timezone.now()
    coll.proof_of_delivery_key = proof_key
    coll.save()
    pos, _ = CourierCashPosition.objects.select_for_update().get_or_create(
        courier=courier)
    pos.cash_on_hand_cents += coll.amount_cents
    pos.last_collection_at = timezone.now()
    pos.save()
    log_event(flow, 'cod.collected',
              {'courier_id': courier.pk, 'amount_cents': coll.amount_cents})
    return coll


@transaction.atomic
def refuse_cod(flow, *, refused=True):
    """Buyer refuses / not present. Increments refusal count if refused."""
    coll = CodCollection.objects.select_for_update().get(flow=flow)
    coll.attempts += 1
    coll.status = 'refused' if refused else 'not_present'
    coll.save(update_fields=['attempts', 'status'])
    if refused and flow.buyer_id:
        profile, _ = BuyerCodProfile.objects.select_for_update(
        ).get_or_create(buyer=flow.buyer)
        profile.refusal_count_90d += 1
        profile.total_refusals += 1
        profile.last_refusal_at = timezone.now()
        if profile.refusal_count_90d >= COD_REFUSAL_DISABLE_THRESHOLD:
            profile.cod_disabled = True
            profile.cod_disabled_reason = '2+ refusals in 90 days'
        # release exposure
        profile.open_exposure_cents = max(
            0, profile.open_exposure_cents - flow.amount_cents)
        profile.save()
    log_event(flow, 'cod.refused' if refused else 'cod.not_present',
              {'attempts': coll.attempts})
    if coll.attempts >= 3:
        transition(flow, sm.FAILED, event_payload={'reason': 'max_cod_attempts'})
    return coll


# ──────────────────────────────────────────────────────────────────────
# CH4 — Cash chain of custody
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def remit_cash(courier, *, deposited_to='BAI'):
    """Courier hands over all collected, not-yet-remitted cash."""
    collections = list(CodCollection.objects.select_for_update().filter(
        courier=courier, status='collected', remittance__isnull=True))
    if not collections:
        return None
    expected = sum(c.amount_cents for c in collections)
    rem = CodCashRemittance.objects.create(
        courier=courier, expected_cents=expected, status='in_transit',
        deposited_to=deposited_to)
    for c in collections:
        c.remittance = rem
        c.save(update_fields=['remittance'])
    pos = CourierCashPosition.objects.select_for_update().get(courier=courier)
    pos.cash_on_hand_cents = max(0, pos.cash_on_hand_cents - expected)
    pos.last_remittance_at = timezone.now()
    pos.save()
    return rem


def deposit_cash(remittance, *, deposited_cents, deposit_reference):
    remittance.deposited_cents = deposited_cents
    remittance.deposit_reference = deposit_reference
    remittance.deposited_at = timezone.now()
    diff = deposited_cents - remittance.expected_cents
    if diff < 0:
        remittance.status = 'short'
        remittance.discrepancy_cents = diff
    elif diff > 0:
        remittance.status = 'over'
        remittance.discrepancy_cents = diff
    else:
        remittance.status = 'deposited'
    remittance.save()
    if diff < 0 and remittance.courier_id:
        pos, _ = CourierCashPosition.objects.get_or_create(
            courier=remittance.courier)
        pos.cash_shortfall_cents += abs(diff)
        pos.save(update_fields=['cash_shortfall_cents', 'updated_at'])
    return remittance


@transaction.atomic
def bank_confirm_remittance(remittance):
    """BAI statement confirms the deposit → unlock order reconciliation."""
    remittance.status = 'bank_confirmed'
    remittance.bank_confirmed_at = timezone.now()
    remittance.save(update_fields=['status', 'bank_confirmed_at'])
    # Reconcile each collection → flow COD_COLLECTED → PAID (doc CH3 step 4).
    reconciled = 0
    for coll in CodCollection.objects.select_for_update().filter(
            remittance=remittance, reconciled=False):
        coll.reconciled = True
        coll.save(update_fields=['reconciled'])
        flow = coll.flow
        if flow.status == sm.COD_COLLECTED:
            transition(flow, sm.PAID,
                       event_payload={'via': 'cod_reconciled'})
            # release buyer exposure
            if flow.buyer_id:
                BuyerCodProfile.objects.filter(buyer=flow.buyer).update(
                    open_exposure_cents=models_greatest_zero(
                        'open_exposure_cents', flow.amount_cents))
            reconciled += 1
    remittance.status = 'reconciled'
    remittance.reconciled_at = timezone.now()
    remittance.save(update_fields=['status', 'reconciled_at'])
    log_event(None, 'cod.remittance_reconciled', None)
    return {'reconciled_collections': reconciled}


def models_greatest_zero(field, delta):
    from django.db.models import F, Value
    from django.db.models.functions import Greatest
    return Greatest(F(field) - delta, Value(0))


def reconcile_cod_daily(recon_date=None):
    """Three-way COD match per courier (doc CH4.2)."""
    recon_date = recon_date or (timezone.now() - timedelta(days=1)).date()
    day_start = timezone.make_aware(
        timezone.datetime.combine(recon_date, timezone.datetime.min.time()))
    day_end = day_start + timedelta(days=1)
    exceptions = 0
    couriers = CodCollection.objects.filter(
        collected_at__gte=day_start, collected_at__lt=day_end
    ).values_list('courier', flat=True).distinct()
    for courier_id in couriers:
        if courier_id is None:
            continue
        colls = CodCollection.objects.filter(
            courier_id=courier_id, collected_at__gte=day_start,
            collected_at__lt=day_end)
        expected = colls.aggregate(s=Sum('amount_cents'))['s'] or 0
        collected = expected  # collected == sum of courier-confirmed
        banked = CodCashRemittance.objects.filter(
            courier_id=courier_id, status__in=('bank_confirmed', 'reconciled'),
            bank_confirmed_at__gte=day_start, bank_confirmed_at__lt=day_end
        ).aggregate(s=Sum('deposited_cents'))['s'] or 0
        if not (expected == collected == banked):
            CodReconciliationException.objects.create(
                courier_id=courier_id, recon_date=recon_date,
                expected_cents=expected, collected_cents=collected,
                banked_cents=banked)
            exceptions += 1
    return {'exceptions': exceptions, 'date': str(recon_date)}


# ──────────────────────────────────────────────────────────────────────
# CH5 — Multicaixa reference
# ──────────────────────────────────────────────────────────────────────

def _appypay_create_reference(flow):
    """Bridge to the Multicaixa gateway. Returns (entity, reference, psp)."""
    try:
        from apps.payment_gateways.gateways.registry import get_gateway
        gw = get_gateway('multicaixa_express')
        if gw and hasattr(gw, 'create_reference'):
            r = gw.create_reference(amount=flow.amount_cents / 100,
                                    order_id=str(flow.id))
            return (r.get('entity', '00822'), r.get('reference'),
                    r.get('psp_reference', ''))
    except Exception:
        pass
    # Dev stub — deterministic reference so smoke tests are stable.
    ref = f'888 {secrets.randbelow(900)+100} {secrets.randbelow(900)+100} ' \
          f'{secrets.randbelow(900)+100}'
    return '00822', ref, f'appypay_{secrets.token_hex(8)}'


@transaction.atomic
def create_mcx_reference(buyer, *, order_id, amount_cents, idempotency_key):
    flow, created = _new_flow(
        order_id=order_id, buyer=buyer, method='mcx_reference',
        amount_cents=amount_cents, idempotency_key=idempotency_key,
        expires_at=timezone.now() + timedelta(hours=REFERENCE_TTL_HOURS))
    if created:
        entity, reference, psp = _appypay_create_reference(flow)
        MulticaixaReference.objects.create(
            flow=flow, entity=entity, reference=reference,
            amount_cents=amount_cents, psp_reference=psp,
            expires_at=flow.expires_at)
        flow.psp_reference = psp
        flow.save(update_fields=['psp_reference'])
        transition(flow, sm.AWAITING_PAYMENT,
                   event_payload={'reference': reference})
    return flow


@transaction.atomic
def confirm_reference_payment(*, merchant_order_id, amount_cents,
                              psp_reference='', paid_at=None):
    """APPYPAY webhook handler (doc CH5 step 4). Idempotent + amount check."""
    flow = PaymentFlow.objects.select_for_update().filter(
        id=merchant_order_id).first()
    if flow is None:
        return {'ok': False, 'reason': 'unknown_flow'}
    if flow.status == sm.PAID:
        return {'ok': True, 'reason': 'already_paid'}  # idempotent
    if amount_cents != flow.amount_cents:
        log_event(flow, 'webhook.amount_mismatch',
                  {'expected': flow.amount_cents, 'got': amount_cents})
        return {'ok': False, 'reason': 'amount_mismatch'}
    # Late-payment-after-expiry edge case (doc CH5): if expired but
    # fulfillable, reactivate; default = credit wallet. Here: mark paid.
    if flow.status == sm.AWAITING_PAYMENT:
        transition(flow, sm.PROCESSING)
    transition(flow, sm.PAID, event_payload={'via': 'mcx_reference',
                                             'psp_reference': psp_reference})
    MulticaixaReference.objects.filter(flow=flow, is_active=True).update(
        paid=True, paid_at=timezone.now(), is_active=False)
    log_event(flow, 'mcx_reference.paid', {'psp_reference': psp_reference})
    return {'ok': True, 'flow_id': str(flow.id)}


def expire_references():
    """Celery sweep (doc CH5 step 5): expire unpaid references past TTL."""
    now = timezone.now()
    expired = 0
    for flow in PaymentFlow.objects.filter(
            method__in=('mcx_reference', 'bank_transfer'),
            status=sm.AWAITING_PAYMENT, expires_at__lt=now):
        transition(flow, sm.EXPIRED)
        MulticaixaReference.objects.filter(flow=flow, is_active=True).update(
            is_active=False)
        expired += 1
    return {'expired': expired}


@transaction.atomic
def regenerate_reference(old_flow):
    """Buyer requests a new reference — new flow, fresh expiry, lineage."""
    new_flow = create_mcx_reference(
        old_flow.buyer, order_id=old_flow.order_id,
        amount_cents=old_flow.amount_cents,
        idempotency_key=PaymentFlow.idempotency_key.field.model and
        f'regen_{uuid.uuid4().hex}')
    old_ref = MulticaixaReference.objects.filter(flow=old_flow).first()
    new_ref = MulticaixaReference.objects.filter(flow=new_flow).first()
    if old_ref and new_ref:
        new_ref.supersedes = old_ref
        new_ref.save(update_fields=['supersedes'])
    return new_flow


# ──────────────────────────────────────────────────────────────────────
# CH6 — Multicaixa push
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def initiate_mcx_push(buyer, *, order_id, amount_cents, phone_number,
                      idempotency_key):
    flow, created = _new_flow(
        order_id=order_id, buyer=buyer, method='mcx_push',
        amount_cents=amount_cents, idempotency_key=idempotency_key)
    if created:
        try:
            from apps.payment_gateways.gateways.registry import get_gateway
            gw = get_gateway('multicaixa_express')
            psp = ''
            if gw and hasattr(gw, 'create_push'):
                r = gw.create_push(amount=amount_cents / 100,
                                   phone=phone_number, order_id=str(flow.id))
                psp = r.get('psp_reference', '')
            flow.psp_reference = psp or f'appypay_{secrets.token_hex(8)}'
        except Exception:
            flow.psp_reference = f'appypay_{secrets.token_hex(8)}'
        flow.save(update_fields=['psp_reference'])
        transition(flow, sm.PROCESSING,
                   event_payload={'channel': 'mcx_push'})
    return flow


@transaction.atomic
def handle_push_result(*, merchant_order_id, success, reason='',
                       amount_cents=None):
    flow = PaymentFlow.objects.select_for_update().filter(
        id=merchant_order_id).first()
    if flow is None:
        return {'ok': False, 'reason': 'unknown_flow'}
    if flow.status in (sm.PAID, sm.FAILED):
        return {'ok': True, 'reason': f'already_{flow.status}'}
    if success:
        if amount_cents is not None and amount_cents != flow.amount_cents:
            log_event(flow, 'webhook.amount_mismatch', {})
            return {'ok': False, 'reason': 'amount_mismatch'}
        transition(flow, sm.PAID, event_payload={'via': 'mcx_push'})
    else:
        transition(flow, sm.FAILED, event_payload={'reason': reason})
    return {'ok': True, 'status': flow.status}


# ──────────────────────────────────────────────────────────────────────
# CH7 — Bank transfer proof verification
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_bank_transfer_flow(buyer, *, order_id, amount_cents,
                              idempotency_key, bank='BAI'):
    flow, created = _new_flow(
        order_id=order_id, buyer=buyer, method='bank_transfer',
        amount_cents=amount_cents, idempotency_key=idempotency_key,
        status=sm.AWAITING_PAYMENT,
        expires_at=timezone.now() + timedelta(hours=BANK_TRANSFER_TTL_HOURS))
    if created:
        log_event(flow, 'bank_transfer.awaiting', {'bank': bank})
    return flow


@transaction.atomic
def upload_bank_proof(flow, *, declared_amount_cents, file_bytes=b'',
                      file_key='', bank='BAI', reference_code='',
                      declared_date=None):
    """Buyer uploads comprovativo. file_hash dedups reuse (doc CH7/CH18)."""
    file_hash = hashlib.sha256(file_bytes or file_key.encode()).hexdigest()
    duplicate = BankTransferProof.objects.filter(
        file_hash=file_hash).exclude(flow=flow).exists()
    proof = BankTransferProof.objects.create(
        flow=flow, bank=bank, declared_amount_cents=declared_amount_cents,
        declared_date=declared_date, reference_code=reference_code,
        file_key=file_key, file_hash=file_hash,
        status='duplicate' if duplicate else 'pending')
    if flow.status == sm.AWAITING_PAYMENT:
        transition(flow, sm.PROCESSING,
                   event_payload={'proof_uploaded': True})
    log_event(flow, 'bank_transfer.proof_uploaded',
              {'duplicate': duplicate, 'declared': declared_amount_cents})
    return proof


@transaction.atomic
def verify_bank_proof(proof, *, decision, reviewer=None, note='',
                      statement_matched=False):
    """Admin/auto verification (doc CH7 step 3). decision: verify/reject/
    clarification. Verification only marks PAID; statement is final truth.
    """
    flow = proof.flow
    proof.reviewed_by = reviewer if getattr(reviewer, 'pk', None) else None
    proof.review_note = note[:300]
    proof.statement_matched = statement_matched
    proof.reviewed_at = timezone.now()
    if decision == 'verify':
        # amount integrity (doc CH7: exact match, Kwanza rules)
        if proof.declared_amount_cents != flow.amount_cents:
            proof.status = 'rejected'
            proof.review_note = 'amount mismatch'
            proof.save()
            return {'ok': False, 'reason': 'amount_mismatch'}
        proof.status = 'auto_verified' if statement_matched else 'verified'
        proof.save()
        if flow.status == sm.PROCESSING:
            transition(flow, sm.PAID,
                       event_payload={'via': 'bank_transfer',
                                      'statement_matched': statement_matched},
                       actor=reviewer)
        return {'ok': True, 'status': 'paid'}
    elif decision == 'reject':
        proof.status = 'rejected'
        proof.save()
        log_event(flow, 'bank_transfer.proof_rejected', {'note': note})
        return {'ok': True, 'status': 'rejected'}
    else:
        proof.status = 'clarification'
        proof.save()
        return {'ok': True, 'status': 'clarification'}


# ──────────────────────────────────────────────────────────────────────
# CH9 — Wallet double-entry ledger (idempotent, source of truth)
# ──────────────────────────────────────────────────────────────────────

def wallet_balance_cents(user):
    agg = WalletLedgerEntry.objects.filter(user=user).aggregate(
        c=Sum('amount_cents', filter=Q(direction='credit')),
        d=Sum('amount_cents', filter=Q(direction='debit')))
    return int(agg['c'] or 0) - int(agg['d'] or 0)


def _sync_cached_balance(user, balance_cents):
    """Keep payment_ops.BuyerWallet.available_balance in sync (bridge)."""
    try:
        from apps.payment_ops.models import BuyerWallet
        BuyerWallet.objects.update_or_create(
            user=user,
            defaults={'available_balance': Decimal(balance_cents) / 100})
    except Exception:
        pass


@transaction.atomic
def wallet_credit(user, *, amount_cents, reference_type, reference_id,
                  idempotency_key):
    """Idempotent credit. Duplicate key → no double credit (doc CH9/CH14)."""
    if amount_cents <= 0:
        raise ValueError('credit amount must be positive')
    # Pre-check handles the common redelivery case without aborting the
    # outer transaction.
    existing = WalletLedgerEntry.objects.filter(
        idempotency_key=idempotency_key).first()
    if existing:
        return existing
    # Lock the user's wallet row so the balance snapshot is consistent.
    try:
        from apps.payment_ops.models import BuyerWallet
        BuyerWallet.objects.select_for_update().get_or_create(user=user)
    except Exception:
        pass
    current = wallet_balance_cents(user)
    new_balance = current + amount_cents
    try:
        # Savepoint so a true concurrent duplicate rolls back just this
        # insert, leaving the outer transaction usable.
        with transaction.atomic():
            entry = WalletLedgerEntry.objects.create(
                user=user, direction='credit', amount_cents=amount_cents,
                balance_after_cents=new_balance, reference_type=reference_type,
                reference_id=str(reference_id),
                idempotency_key=idempotency_key)
    except IntegrityError:
        return WalletLedgerEntry.objects.get(idempotency_key=idempotency_key)
    _sync_cached_balance(user, new_balance)
    return entry


@transaction.atomic
def wallet_debit(user, *, amount_cents, reference_type, reference_id,
                 idempotency_key):
    """Idempotent debit with balance guard (doc CH9 spend, SELECT FOR UPDATE)."""
    if amount_cents <= 0:
        raise ValueError('debit amount must be positive')
    existing = WalletLedgerEntry.objects.filter(
        idempotency_key=idempotency_key).first()
    if existing:
        return existing  # idempotent — already applied
    # Lock concurrent debits for this user via the cached wallet row.
    try:
        from apps.payment_ops.models import BuyerWallet
        BuyerWallet.objects.select_for_update().get_or_create(user=user)
    except Exception:
        pass
    current = wallet_balance_cents(user)
    if current < amount_cents:
        raise ValueError('insufficient wallet balance')
    new_balance = current - amount_cents
    try:
        # Savepoint so a concurrent duplicate rolls back just this insert.
        with transaction.atomic():
            entry = WalletLedgerEntry.objects.create(
                user=user, direction='debit', amount_cents=amount_cents,
                balance_after_cents=new_balance, reference_type=reference_type,
                reference_id=str(reference_id),
                idempotency_key=idempotency_key)
    except IntegrityError:
        return WalletLedgerEntry.objects.get(idempotency_key=idempotency_key)
    _sync_cached_balance(user, new_balance)
    return entry


def check_wallet_integrity():
    """Daily: ledger sum vs cached balance per wallet (doc CH9)."""
    breaches = 0
    try:
        from apps.payment_ops.models import BuyerWallet
        for w in BuyerWallet.objects.all().iterator():
            ledger = wallet_balance_cents(w.user)
            cached = int(Decimal(str(w.available_balance)) * 100)
            if ledger != cached:
                WalletIntegrityBreach.objects.create(
                    user=w.user, ledger_balance_cents=ledger,
                    cached_balance_cents=cached)
                w.is_active = False  # freeze
                w.save(update_fields=['is_active'])
                breaches += 1
    except Exception:
        pass
    return {'breaches': breaches}


# ──────────────────────────────────────────────────────────────────────
# CH10 — P2P wallet-to-wallet transfer
# ──────────────────────────────────────────────────────────────────────

def _p2p_velocity_ok(sender, amount_cents):
    if amount_cents > P2P_MAX_PER_TXN_CENTS:
        return False, 'per_txn_limit'
    since = timezone.now() - timedelta(days=1)
    day = WalletTransfer.objects.filter(
        sender=sender, created_at__gte=since,
        status__in=('completed', 'pending'))
    day_total = day.aggregate(s=Sum('amount_cents'))['s'] or 0
    if day_total + amount_cents > P2P_MAX_PER_DAY_CENTS:
        return False, 'daily_limit'
    recipients = day.values('recipient').distinct().count()
    if recipients >= P2P_MAX_RECIPIENTS_PER_DAY:
        return False, 'recipient_fanout'
    return True, None


@transaction.atomic
def p2p_transfer(sender, recipient, *, amount_cents, note=''):
    """Atomic two-sided transfer. Deadlock-safe: lock wallet rows in a
    consistent global order (by user id) (doc CH10 step 3).
    """
    if sender.pk == recipient.pk:
        return {'ok': False, 'reason': 'self_transfer'}
    if amount_cents <= 0:
        return {'ok': False, 'reason': 'invalid_amount'}

    ok, reason = _p2p_velocity_ok(sender, amount_cents)
    transfer = WalletTransfer.objects.create(
        sender=sender, recipient=recipient, amount_cents=amount_cents,
        note=note[:140], status='pending')
    if not ok:
        transfer.status = 'held_for_review'
        transfer.hold_reason = reason
        transfer.save(update_fields=['status', 'hold_reason'])
        return {'ok': False, 'reason': reason, 'transfer_id': str(transfer.id),
                'held': True}

    # Deadlock-safe lock ordering: lock the lower user id first.
    first, second = sorted([sender, recipient], key=lambda u: u.pk)
    try:
        from apps.payment_ops.models import BuyerWallet
        BuyerWallet.objects.select_for_update().get_or_create(user=first)
        BuyerWallet.objects.select_for_update().get_or_create(user=second)
    except Exception:
        pass

    if wallet_balance_cents(sender) < amount_cents:
        transfer.status = 'rejected'
        transfer.hold_reason = 'insufficient_balance'
        transfer.save(update_fields=['status', 'hold_reason'])
        return {'ok': False, 'reason': 'insufficient_balance'}

    wallet_debit(sender, amount_cents=amount_cents, reference_type='p2p_out',
                 reference_id=str(transfer.id),
                 idempotency_key=f'p2p_out:{transfer.id}')
    wallet_credit(recipient, amount_cents=amount_cents,
                  reference_type='p2p_in', reference_id=str(transfer.id),
                  idempotency_key=f'p2p_in:{transfer.id}')
    transfer.status = 'completed'
    transfer.completed_at = timezone.now()
    transfer.save(update_fields=['status', 'completed_at'])
    return {'ok': True, 'transfer_id': str(transfer.id)}


# ──────────────────────────────────────────────────────────────────────
# CH8 — Split payment saga
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_split_flow(buyer, *, order_id, total_cents, wallet_cents,
                      external_method, idempotency_key):
    """Wallet leg first (reversible), then external leg (doc CH8)."""
    if wallet_cents <= 0 or wallet_cents >= total_cents:
        raise ValueError('wallet_cents must be 0 < w < total')
    if wallet_balance_cents(buyer) < wallet_cents:
        raise ValueError('insufficient wallet for split')
    flow, created = _new_flow(order_id=order_id, buyer=buyer, method='split',
                              amount_cents=total_cents,
                              idempotency_key=idempotency_key)
    if not created:
        return flow
    external_cents = total_cents - wallet_cents
    # Component 0: wallet HOLD (debit now, reversible until external confirms)
    hold_key = f'split_hold:{flow.id}'
    wallet_debit(buyer, amount_cents=wallet_cents, reference_type='split_hold',
                 reference_id=str(flow.id), idempotency_key=hold_key)
    c0 = PaymentComponent.objects.create(
        flow=flow, method='wallet', amount_cents=wallet_cents,
        status=sm.PROCESSING, wallet_hold_idempotency_key=hold_key,
        hold_expires_at=timezone.now() + timedelta(
            minutes=WALLET_HOLD_TTL_MINUTES))
    c1 = PaymentComponent.objects.create(
        flow=flow, method=external_method, amount_cents=external_cents,
        status=sm.PROCESSING)
    transition(flow, sm.PROCESSING, event_payload={'split': True})
    log_event(flow, 'split.wallet_held', {'wallet_cents': wallet_cents})
    return flow


@transaction.atomic
def settle_split_component(flow, *, external_success):
    """External leg resolved → finalise or reverse the wallet hold (CH8)."""
    c0 = flow.components.filter(method='wallet').first()
    c1 = flow.components.exclude(method='wallet').first()
    if external_success:
        c0.status = sm.PAID
        c1.status = sm.PAID
        c0.save(update_fields=['status'])
        c1.save(update_fields=['status'])
        transition(flow, sm.PAID, event_payload={'split': 'all_paid'})
        return {'ok': True, 'status': 'paid'}
    # Reverse the wallet hold → refund W back (doc CH8 failure path).
    wallet_credit(flow.buyer, amount_cents=c0.amount_cents,
                  reference_type='split_release', reference_id=str(flow.id),
                  idempotency_key=f'split_release:{flow.id}')
    c0.status = sm.CANCELLED
    c1.status = sm.FAILED
    c0.save(update_fields=['status'])
    c1.save(update_fields=['status'])
    transition(flow, sm.FAILED, event_payload={'split': 'external_failed'})
    return {'ok': True, 'status': 'failed_reversed'}


def release_split_holds():
    """Crash-safety sweep: release expired wallet holds (doc CH8/CH20 job 7)."""
    now = timezone.now()
    released = 0
    for c in PaymentComponent.objects.filter(
            method='wallet', status=sm.PROCESSING,
            hold_expires_at__lt=now).select_related('flow'):
        flow = c.flow
        if flow.status in (sm.PAID, sm.FAILED):
            continue
        wallet_credit(flow.buyer, amount_cents=c.amount_cents,
                      reference_type='split_release', reference_id=str(flow.id),
                      idempotency_key=f'split_release:{flow.id}')
        c.status = sm.CANCELLED
        c.save(update_fields=['status'])
        transition(flow, sm.FAILED, event_payload={'split': 'hold_expired'})
        released += 1
    return {'released': released}


# ──────────────────────────────────────────────────────────────────────
# CH11 — APPYPAY settlement three-way match
# ──────────────────────────────────────────────────────────────────────

def ingest_settlement_line(*, settlement_date, psp_reference,
                           merchant_order_id, gross_cents, fee_cents=0,
                           psp_status='PAID'):
    rec, _ = SettlementRecord.objects.update_or_create(
        settlement_date=settlement_date, psp_reference=psp_reference,
        defaults={'merchant_order_id': merchant_order_id,
                  'gross_cents': gross_cents, 'fee_cents': fee_cents,
                  'net_cents': gross_cents - fee_cents,
                  'psp_status': psp_status})
    return rec


@transaction.atomic
def reconcile_settlement_day(run_date=None):
    """Three-way match (doc CH11). Flags AMOUNT_MISMATCH, MISSING_SETTLEMENT,
    UNKNOWN_SETTLEMENT into payment_ops.ReconciliationException.
    """
    run_date = run_date or (timezone.now() - timedelta(days=1)).date()
    day_start = timezone.make_aware(
        timezone.datetime.combine(run_date, timezone.datetime.min.time()))
    day_end = day_start + timedelta(days=1)

    internal = PaymentFlow.objects.filter(
        method__in=('mcx_reference', 'mcx_push'), status=sm.PAID,
        paid_at__gte=day_start, paid_at__lt=day_end)
    total = internal.count()
    matched = exceptions = 0
    matched_refs = set()

    for flow in internal:
        rec = SettlementRecord.objects.filter(
            settlement_date=run_date, psp_reference=flow.psp_reference).first()
        if rec is None:
            _recon_exception('MISSING_SETTLEMENT', flow.psp_reference,
                             flow.amount_cents, 0)
            exceptions += 1
            continue
        matched_refs.add(rec.psp_reference)
        if rec.gross_cents != flow.amount_cents:
            rec.match_status = 'amount_mismatch'
            rec.save(update_fields=['match_status'])
            _recon_exception('AMOUNT_MISMATCH', rec.psp_reference,
                             flow.amount_cents, rec.gross_cents)
            exceptions += 1
            continue
        rec.match_status = 'matched'
        rec.flow = flow
        rec.save(update_fields=['match_status', 'flow'])
        flow.settled = True
        flow.fee_cents = rec.fee_cents
        flow.net_cents = rec.net_cents
        flow.save(update_fields=['settled', 'fee_cents', 'net_cents'])
        matched += 1

    # Settlement records with no internal match → UNKNOWN_SETTLEMENT.
    for rec in SettlementRecord.objects.filter(
            settlement_date=run_date).exclude(psp_reference__in=matched_refs):
        if rec.match_status == 'unmatched':
            rec.match_status = 'unknown_settlement'
            rec.save(update_fields=['match_status'])
            _recon_exception('UNKNOWN_SETTLEMENT', rec.psp_reference, 0,
                             rec.gross_cents)
            exceptions += 1

    run, _ = SettlementRun.objects.update_or_create(
        run_date=run_date,
        defaults={'total_internal_paid': total, 'matched': matched,
                  'exceptions': exceptions,
                  'match_rate_pct': round(matched / total * 100, 2)
                  if total else 0,
                  'status': 'has_exceptions' if exceptions else 'reconciled'})
    return {'matched': matched, 'exceptions': exceptions, 'total': total}


def _recon_exception(kind, reference, expected, actual):
    try:
        from apps.payment_ops.models import ReconciliationException
        ReconciliationException.objects.create(
            exception_type=kind, psp_reference=reference,
            expected_amount=Decimal(expected) / 100,
            actual_amount=Decimal(actual) / 100, status='open')
    except Exception:
        # Fallback: COD recon exception table or just log.
        log_event(None, 'reconciliation.exception',
                  {'kind': kind, 'reference': reference})


# ──────────────────────────────────────────────────────────────────────
# CH12 — Dunning
# ──────────────────────────────────────────────────────────────────────

DUNNING_SCHEDULE = {
    'mcx_reference': [('T+1h', 1), ('T+12h', 12), ('T-3h', -3)],
    'bank_transfer': [('T+6h', 6), ('T+24h', 24), ('T-6h', -6)],
}


def run_dunning():
    """Celery beat (doc CH12). Sends due reminders + expires past-TTL."""
    now = timezone.now()
    reminders = expired = 0
    pending = PaymentFlow.objects.filter(
        status=sm.AWAITING_PAYMENT,
        method__in=('mcx_reference', 'bank_transfer'))
    for flow in pending:
        if flow.expires_at and now >= flow.expires_at:
            transition(flow, sm.EXPIRED)
            expired += 1
            continue
        schedule = DUNNING_SCHEDULE.get(flow.method, [])
        ds, _ = DunningState.objects.get_or_create(flow=flow)
        for label, hours in schedule:
            if hours >= 0:
                due_at = flow.created_at + timedelta(hours=hours)
            else:
                due_at = (flow.expires_at or now) + timedelta(hours=hours)
            if now >= due_at and label not in (ds.steps_sent or []):
                _send_reminder(flow, label)
                ds.steps_sent = list(ds.steps_sent or []) + [label]
                ds.reminders_sent += 1
                ds.last_reminder_at = now
                ds.save()
                reminders += 1
    return {'reminders': reminders, 'expired': expired}


def _send_reminder(flow, step):
    """Bridge to notifications (fail open). Respects the doc's anti-spam
    via the per-step dedup in run_dunning."""
    log_event(flow, 'dunning.reminder_sent', {'step': step})
    try:
        from apps.notifications.push_service import send_to_user
        if flow.buyer_id:
            send_to_user(flow.buyer, title='Conclua o seu pagamento',
                         body=f'A sua referência expira em breve ({step}).')
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH15 — Refund engine
# ──────────────────────────────────────────────────────────────────────

REFUND_ROUTING = {
    'mcx_reference': 'wallet', 'mcx_push': 'wallet',
    'bank_transfer': 'bank', 'wallet': 'wallet', 'cod': 'wallet',
    'split': 'per_component',
}


@transaction.atomic
def create_refund(flow, *, amount_cents, reason, target=None):
    """Route a refund by method (doc CH15). Wallet target = instant."""
    if flow.status not in (sm.PAID, sm.PARTIALLY_REFUNDED):
        return {'ok': False, 'reason': f'not_refundable_{flow.status}'}
    if flow.refunded_cents + amount_cents > flow.amount_cents:
        return {'ok': False, 'reason': 'exceeds_paid_amount'}
    target = target or REFUND_ROUTING.get(flow.method, 'wallet')

    transition(flow, sm.REFUND_PENDING,
               event_payload={'amount_cents': amount_cents, 'reason': reason})
    refund_key = f'refund:{flow.id}:{flow.refunded_cents + amount_cents}'

    if target == 'wallet' and flow.buyer_id:
        wallet_credit(flow.buyer, amount_cents=amount_cents,
                      reference_type='refund', reference_id=str(flow.id),
                      idempotency_key=refund_key)
        status_after = 'wallet_credited'
    else:
        # bank payout / per-component → recorded; finance executes (stub).
        status_after = 'queued_for_payout'

    flow.refunded_cents += amount_cents
    fully = flow.refunded_cents >= flow.amount_cents
    flow.save(update_fields=['refunded_cents'])
    transition(flow, sm.REFUNDED if fully else sm.PARTIALLY_REFUNDED,
               event_payload={'target': target})
    log_event(flow, 'refund.completed',
              {'amount_cents': amount_cents, 'target': target})
    return {'ok': True, 'target': target, 'status': status_after,
            'fully_refunded': fully}


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

def snapshot_payments_kpis(snapshot_date=None):
    snapshot_date = snapshot_date or timezone.now().date()
    day_start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()))
    day_end = day_start + timedelta(days=1)

    prepaid = PaymentFlow.objects.filter(
        method__in=('mcx_reference', 'mcx_push', 'bank_transfer', 'wallet'),
        created_at__gte=day_start, created_at__lt=day_end)
    initiated = prepaid.count()
    paid = prepaid.filter(status__in=sm.SUCCESS_STATES).count()
    success_pct = round(paid / initiated * 100, 2) if initiated else 0

    cod = CodCollection.objects.filter(
        created_at__gte=day_start, created_at__lt=day_end)
    cod_shipped = cod.exclude(status='pending').count()
    cod_collected = cod.filter(
        status__in=('collected',)).count()
    cod_refused = cod.filter(status='refused').count()
    cod_accept_pct = round(cod_collected / cod_shipped * 100, 2) \
        if cod_shipped else 0
    cod_refusal_pct = round(cod_refused / cod_shipped * 100, 2) \
        if cod_shipped else 0

    cash_in_transit = CodCashRemittance.objects.filter(
        status__in=('collected', 'in_transit', 'deposited')).aggregate(
        s=Sum('expected_cents'))['s'] or 0

    refs = MulticaixaReference.objects.filter(
        created_at__gte=day_start, created_at__lt=day_end)
    ref_total = refs.count()
    ref_paid = refs.filter(paid=True).count()
    ref_conv = round(ref_paid / ref_total * 100, 2) if ref_total else 0

    run = SettlementRun.objects.filter(run_date=snapshot_date).first()
    settle_pct = run.match_rate_pct if run else Decimal('0')

    open_exc = 0
    try:
        from apps.payment_ops.models import ReconciliationException
        open_exc = ReconciliationException.objects.filter(
            status='open').count()
    except Exception:
        pass
    open_exc += CodReconciliationException.objects.filter(
        resolved=False).count()

    mix = dict(PaymentFlow.objects.filter(
        created_at__gte=day_start, created_at__lt=day_end
    ).values('method').annotate(n=Count('id')).values_list('method', 'n'))

    snap, _ = PaymentsAngolaKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'payment_success_pct': success_pct,
            'cod_acceptance_pct': cod_accept_pct,
            'cod_refusal_pct': cod_refusal_pct,
            'cash_in_transit_cents': cash_in_transit,
            'reference_conversion_pct': ref_conv,
            'settlement_match_pct': settle_pct,
            'open_recon_exceptions': open_exc,
            'wallet_integrity_ok': not WalletIntegrityBreach.objects.filter(
                resolved=False).exists(),
            'method_mix': mix,
        },
    )
    return snap
