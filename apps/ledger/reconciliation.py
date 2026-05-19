"""
apps/ledger/reconciliation.py
─────────────────────────────

Periodic and on-demand invariant checks for the ledger.

The write-side already enforces the double-entry invariant via
``service.post()`` — every journal must have ``sum(debits) ==
sum(credits)`` or it's rejected. That's necessary but not sufficient
for a production platform at scale.

Three drift modes happen in real-world commerce platforms even with
a perfect write-side:

  1. **Cached-counter drift.** ``User.store_credit`` is a Decimal
     column kept for fast read paths. The ledger is the source of
     truth. Any code path that updates ``user.store_credit`` WITHOUT
     also posting to the ledger creates drift. Same for
     ``User.loyalty_points`` and ``SellerWallet.balance``.

  2. **Global imbalance.** Sum of all credits minus sum of all debits
     across the entire ledger should be zero (every value created
     comes from another account). If it isn't, something has gone
     deeply wrong — direct SQL by an operator, a forgotten signal
     handler, partial restore from backup.

  3. **Journal imbalance.** Individual journals should self-balance.
     ``post()`` enforces this, but if anything ever bypasses post()
     (raw SQL, data migration), the check catches it.

This module provides the queries to detect all three, plus
correction helpers when drift is found.

Why "periodic" — even with a perfect codebase, ops teams want
defence-in-depth verification. Reconciliation reports are also
how auditors confirm financial integrity.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.db.models import Sum, F, Q
from django.utils import timezone

from .models import Account, AccountType, Journal, LedgerEntry, LedgerError
from . import service as ledger_service


log = logging.getLogger(__name__)
User = get_user_model()


# ─── Result dataclasses ───────────────────────────────────────────────────

@dataclass
class GlobalInvariantResult:
    debit_total_cents: int
    credit_total_cents: int
    imbalance_cents: int

    @property
    def is_balanced(self) -> bool:
        return self.imbalance_cents == 0


@dataclass
class UnbalancedJournal:
    journal_id: int
    idempotency_key: str
    debit_total_cents: int
    credit_total_cents: int
    imbalance_cents: int
    ref_type: str
    ref_id: str
    created_at: str


@dataclass
class CachedCounterDrift:
    user_id: int
    user_email: str
    field: str               # 'store_credit' | 'loyalty_points' | 'seller_wallet_balance'
    cached_value: Decimal    # raw value on the User / SellerWallet row
    ledger_balance: Decimal  # derived from LedgerEntry sums
    drift: Decimal           # cached − ledger (positive = cached > ledger)


# ─── Global invariant ─────────────────────────────────────────────────────

def check_global_invariant() -> GlobalInvariantResult:
    """Sum every LedgerEntry's debits and credits.

    For a sound double-entry ledger, debit_total === credit_total
    across the WHOLE table. Any drift here is a five-alarm fire — it
    means either:
      • A journal was written that wasn't balanced (post() bypassed)
      • Entries were deleted out-of-band
      • Partial restore from backup created an open transaction state

    This is cheap (two aggregations) and should run daily.
    """
    totals = LedgerEntry.objects.aggregate(
        debit_total=Sum('debit_cents'),
        credit_total=Sum('credit_cents'),
    )
    debit = int(totals['debit_total'] or 0)
    credit = int(totals['credit_total'] or 0)
    return GlobalInvariantResult(
        debit_total_cents=debit,
        credit_total_cents=credit,
        imbalance_cents=credit - debit,  # positive = excess credits
    )


# ─── Per-journal invariant ────────────────────────────────────────────────

def find_unbalanced_journals(limit: int = 100) -> list[UnbalancedJournal]:
    """Find journals where the line entries don't sum to zero.

    Should ALWAYS be empty in a healthy system because ``post()`` rejects
    unbalanced journals at write time. Non-empty result indicates a
    bypass: raw SQL, data migration, signal handler, etc.

    Strategy: per-journal aggregation, filter rows where debit != credit.
    Result is at most ``limit`` rows — operator triages these by hand.
    """
    qs = (
        LedgerEntry.objects
        .values('journal_id')
        .annotate(
            d=Sum('debit_cents'),
            c=Sum('credit_cents'),
        )
        .filter(~Q(d=F('c')))
        .order_by('-journal_id')[:max(1, min(limit, 1000))]
    )
    journal_ids = [row['journal_id'] for row in qs]
    if not journal_ids:
        return []
    journals = {
        j.id: j for j in Journal.objects.filter(pk__in=journal_ids)
    }
    out: list[UnbalancedJournal] = []
    for row in qs:
        j = journals.get(row['journal_id'])
        if j is None:
            continue
        d = int(row['d'] or 0)
        c = int(row['c'] or 0)
        out.append(UnbalancedJournal(
            journal_id=j.id,
            idempotency_key=j.idempotency_key,
            debit_total_cents=d,
            credit_total_cents=c,
            imbalance_cents=c - d,
            ref_type=j.ref_type or '',
            ref_id=j.ref_id or '',
            created_at=j.created_at.isoformat(),
        ))
    return out


# ─── Cached-counter reconciliation ────────────────────────────────────────

def _cents_to_decimal(cents: int) -> Decimal:
    return Decimal(int(cents)) / Decimal(100)


def reconcile_user_store_credit(user) -> Optional[CachedCounterDrift]:
    """Compare User.store_credit (Decimal AOA) to the ledger truth.

    Ledger truth = balance of the user's USER_STORE_CREDIT account.
    Returns None if balanced, a Drift record otherwise.
    """
    acc = Account.objects.filter(
        type=AccountType.USER_STORE_CREDIT, user=user,
    ).first()
    ledger_cents = acc.balance() if acc else 0
    ledger_value = _cents_to_decimal(ledger_cents)
    cached = Decimal(str(user.store_credit or 0))
    drift = cached - ledger_value
    if drift == 0:
        return None
    return CachedCounterDrift(
        user_id=user.pk, user_email=user.email,
        field='store_credit',
        cached_value=cached, ledger_balance=ledger_value,
        drift=drift,
    )


def reconcile_user_loyalty_points(user) -> Optional[CachedCounterDrift]:
    """User.loyalty_points is integer PTS units; the ledger account
    USER_LOYALTY_POINTS tracks it 1:1 (no /100 conversion)."""
    acc = Account.objects.filter(
        type=AccountType.USER_LOYALTY_POINTS, user=user,
    ).first()
    # Loyalty currency is 'PTS' with 1=1 mapping (not Kz cents).
    # We treat amount_cents as the integer point count directly.
    ledger_points = int(acc.balance()) if acc else 0
    cached = int(user.loyalty_points or 0)
    drift = cached - ledger_points
    if drift == 0:
        return None
    return CachedCounterDrift(
        user_id=user.pk, user_email=user.email,
        field='loyalty_points',
        cached_value=Decimal(cached),
        ledger_balance=Decimal(ledger_points),
        drift=Decimal(drift),
    )


def reconcile_seller_wallet(seller) -> Optional[CachedCounterDrift]:
    """SellerWallet.balance (Decimal AOA) vs SELLER_WALLET account."""
    try:
        from apps.payments.models import SellerWallet
        wallet = SellerWallet.objects.filter(seller=seller).first()
    except Exception:
        return None
    if wallet is None:
        return None
    acc = Account.objects.filter(
        type=AccountType.SELLER_WALLET, user=seller,
    ).first()
    ledger_cents = acc.balance() if acc else 0
    ledger_value = _cents_to_decimal(ledger_cents)
    cached = Decimal(str(wallet.balance or 0))
    drift = cached - ledger_value
    if drift == 0:
        return None
    return CachedCounterDrift(
        user_id=seller.pk, user_email=seller.email,
        field='seller_wallet_balance',
        cached_value=cached, ledger_balance=ledger_value,
        drift=drift,
    )


def reconcile_user(user) -> list[CachedCounterDrift]:
    """All cached counters for one user. Returns a list (0..N drifts)."""
    drifts = []
    for fn in (reconcile_user_store_credit,
               reconcile_user_loyalty_points,
               reconcile_seller_wallet):
        try:
            d = fn(user)
            if d is not None:
                drifts.append(d)
        except Exception:
            log.exception('reconcile_user: %s failed', fn.__name__)
    return drifts


def scan_user_drift(*, batch_size: int = 500,
                    max_users: int = 50_000) -> dict:
    """Bulk scan of cached counters across users.

    Walks Users with non-zero balances first (those are the ones where
    drift would matter — a user with 0 loyalty points isn't going to
    silently drift to 1). Caps at ``max_users`` so a million-user table
    doesn't lock up the worker.

    Returns counts + sample drifts for alerting + ops dashboard.
    """
    drifts: list[CachedCounterDrift] = []
    scanned = 0

    # Scan users with non-zero cached counters first
    interesting = (
        User.objects.filter(
            Q(store_credit__gt=0) | Q(loyalty_points__gt=0),
        )
        .only('pk', 'email', 'store_credit', 'loyalty_points')
        .order_by('pk')
    )
    for batch_start in range(0, max_users, batch_size):
        batch = list(interesting[batch_start:batch_start + batch_size])
        if not batch:
            break
        for u in batch:
            scanned += 1
            drifts.extend(reconcile_user(u))

    # Sellers (separate table)
    try:
        from apps.payments.models import SellerWallet
        wallets = (
            SellerWallet.objects
            .filter(Q(balance__gt=0) | Q(pending_balance__gt=0))
            .select_related('seller')
            .only('seller__pk', 'seller__email', 'balance', 'pending_balance')
        )
        for w in wallets[:max_users]:
            scanned += 1
            d = reconcile_seller_wallet(w.seller)
            if d is not None:
                drifts.append(d)
    except Exception:
        log.exception('scan_user_drift: seller wallet pass failed')

    return {
        'scanned': scanned,
        'drift_count': len(drifts),
        'total_drift_cents': int(sum(
            (d.drift * 100 for d in drifts), Decimal(0),
        )),
        'sample': [
            {
                'user_id': d.user_id, 'email': d.user_email,
                'field': d.field,
                'cached': str(d.cached_value),
                'ledger': str(d.ledger_balance),
                'drift': str(d.drift),
            }
            for d in drifts[:25]
        ],
    }


# ─── Correction helpers ───────────────────────────────────────────────────

def post_correction_journal(*, account, amount_cents: int,
                             direction: str, reason: str,
                             actor=None) -> 'Journal':
    """Post a SINGLE-SIDED correction to bring an account to a known good
    state. Must be balanced against a platform reconciliation account
    (PLATFORM_REFUND_POOL by convention) so the global invariant holds.

    Use ONLY when drift has been detected and the operator has decided
    which value (cached or ledger) is authoritative. The default in this
    codebase is: the LEDGER is the source of truth and the cached
    counter must be reset to match. So corrections happen on the cached
    counter side, NOT here.

    This helper exists for the rare case where the LEDGER is wrong
    (e.g. a partial restore left orphan entries) and needs to be
    adjusted via a properly-audited journal entry.
    """
    if amount_cents <= 0:
        raise LedgerError('correction amount must be positive')
    if direction not in ('debit', 'credit'):
        raise LedgerError(f'direction must be debit/credit, got {direction!r}')

    counterpart = Account.platform(
        AccountType.PLATFORM_REFUND_POOL, currency=account.currency,
    )
    opposite = 'credit' if direction == 'debit' else 'debit'

    key = (
        f'correction:{account.id}:{direction}:{amount_cents}:'
        f'{int(timezone.now().timestamp())}'
    )
    journal, _, _ = ledger_service.post(
        journal_key=key,
        lines=[
            (account, amount_cents, direction),
            (counterpart, amount_cents, opposite),
        ],
        ref_type='correction',
        ref_id=str(account.id),
        description=f'Reconciliation correction: {reason[:200]}',
        user=actor,
    )
    log.warning(
        'ledger.correction: account=%s %s %d cents reason=%s actor=%s',
        account.id, direction, amount_cents, reason, getattr(actor, 'id', None),
    )
    return journal


def reset_cached_counter_to_ledger(user) -> dict:
    """Cached → Ledger reconciliation: rewrite User.store_credit and
    loyalty_points + SellerWallet.balance to match the ledger truth.

    Use when scan_user_drift surfaces a drift and the operator has
    determined the LEDGER is correct (the usual case).

    Idempotent — re-running on a balanced user is a no-op.
    """
    fixed = {}
    # Store credit
    acc = Account.objects.filter(
        type=AccountType.USER_STORE_CREDIT, user=user,
    ).first()
    if acc is not None:
        ledger_value = _cents_to_decimal(acc.balance())
        if Decimal(str(user.store_credit or 0)) != ledger_value:
            User.objects.filter(pk=user.pk).update(store_credit=ledger_value)
            fixed['store_credit'] = str(ledger_value)

    # Loyalty points
    acc = Account.objects.filter(
        type=AccountType.USER_LOYALTY_POINTS, user=user,
    ).first()
    if acc is not None:
        ledger_points = int(acc.balance())
        if int(user.loyalty_points or 0) != ledger_points:
            User.objects.filter(pk=user.pk).update(loyalty_points=ledger_points)
            fixed['loyalty_points'] = ledger_points

    # Seller wallet
    try:
        from apps.payments.models import SellerWallet
        wallet = SellerWallet.objects.filter(seller=user).first()
        if wallet is not None:
            acc = Account.objects.filter(
                type=AccountType.SELLER_WALLET, user=user,
            ).first()
            if acc is not None:
                ledger_value = _cents_to_decimal(acc.balance())
                if Decimal(str(wallet.balance or 0)) != ledger_value:
                    SellerWallet.objects.filter(pk=wallet.pk).update(
                        balance=ledger_value,
                    )
                    fixed['seller_wallet_balance'] = str(ledger_value)
    except Exception:
        log.exception('reset_cached_counter_to_ledger: wallet pass failed')

    log.info(
        'ledger.reset_cached_to_ledger: user=%s fixed=%s',
        user.id, fixed or 'nothing',
    )
    return fixed
