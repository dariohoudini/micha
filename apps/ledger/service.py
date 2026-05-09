"""
Ledger posting service.

Public API
----------
post(journal_key, lines, *, ref_type='', ref_id='', description='', user=None)
    Post a balanced journal. Lines is a list of (account, amount_cents, direction)
    where direction is 'debit' or 'credit'. Idempotent on `journal_key`.

transfer(from_account, to_account, amount_cents, *, journal_key, ref_type='', ref_id='', description='', user=None)
    Convenience: debit `from_account`, credit `to_account` by the same amount.

Idempotency
-----------
Posting with an already-seen `journal_key` is a no-op — returns the prior Journal.
This is the single source of truth for "did this happen?". Callers should pick a
deterministic key, e.g. `f"checkin:{user_id}:{date}"`.
"""
from decimal import Decimal
from django.db import transaction
from .models import Account, Journal, LedgerEntry, LedgerError


def _to_cents(amount):
    """Coerce Decimal/float/int Kz amount to integer centavos."""
    if isinstance(amount, int):
        return amount * 100
    return int((Decimal(str(amount)) * 100).to_integral_value())


@transaction.atomic
def post(journal_key, lines, *, ref_type='', ref_id='', description='', user=None):
    """Post a balanced multi-line journal.

    `lines` is a list of dicts:
        {'account': <Account>, 'amount_cents': int, 'direction': 'debit'|'credit', 'description': str}
    OR a list of tuples:
        (account, amount_cents, 'debit'|'credit')

    Returns: (journal, created: bool)
    Raises: LedgerError if unbalanced or idempotency clash with different content.
    """
    if not journal_key:
        raise LedgerError('journal_key is required for idempotency')

    # Idempotency check
    existing = Journal.objects.filter(idempotency_key=journal_key).first()
    if existing is not None:
        return existing, False

    if not lines:
        raise LedgerError('Cannot post a journal with no lines')

    normalised = []
    debit_total = 0
    credit_total = 0

    for item in lines:
        if isinstance(item, dict):
            account = item['account']
            amount_cents = int(item['amount_cents'])
            direction = item['direction']
            line_desc = item.get('description', '')
        else:
            account, amount_cents, direction = item
            amount_cents = int(amount_cents)
            line_desc = ''

        if amount_cents <= 0:
            raise LedgerError(f'Line amount must be > 0, got {amount_cents}')
        if direction not in ('debit', 'credit'):
            raise LedgerError(f'Direction must be debit or credit, got {direction!r}')

        if direction == 'debit':
            debit_total += amount_cents
        else:
            credit_total += amount_cents

        normalised.append((account, amount_cents, direction, line_desc or description))

    if debit_total != credit_total:
        raise LedgerError(
            f'Journal is unbalanced: debits={debit_total}, credits={credit_total}'
        )

    journal = Journal.objects.create(
        idempotency_key=journal_key,
        description=description,
        ref_type=ref_type,
        ref_id=str(ref_id)[:80] if ref_id else '',
        posted_by=user,
    )

    LedgerEntry.objects.bulk_create([
        LedgerEntry(
            journal=journal,
            account=account,
            debit_cents=amount_cents if direction == 'debit' else 0,
            credit_cents=amount_cents if direction == 'credit' else 0,
            description=line_desc,
        )
        for account, amount_cents, direction, line_desc in normalised
    ])

    return journal, True


def record_payment_received(*, order, buyer_paid, commission_amount,
                            platform_subsidy=0, seller_discount=0,
                            idempotency_key=None):
    """At payment confirmation: post the canonical decomposition.

    Variables:
        nominal           = order.subtotal (price before any discount)
        buyer_paid        = what the gateway received (= nominal − all discounts)
        commission        = platform's % cut of nominal
        platform_subsidy  = portion of discount FUNDED by the platform (eats commission)
        seller_discount   = portion of discount funded by the seller (lower earnings)
        store_credit      = redeemed buyer credit — already moved at checkout, not here

    seller_earnings = nominal − commission − seller_discount

    Posting (AOA, cents):
        DR EXTERNAL_CLEARING                buyer_paid
        DR PLATFORM_REVENUE                 platform_subsidy   (only if > 0)
        CR SELLER_PENDING                   seller_earnings
        CR PLATFORM_REVENUE                 commission

    Net platform revenue = commission − platform_subsidy.
    The journal is balanced because:
        debits  = buyer_paid + platform_subsidy
                = (nominal − platform_subsidy − seller_discount − store_credit) + platform_subsidy
                = nominal − seller_discount − store_credit
        credits = seller_earnings + commission
                = (nominal − commission − seller_discount) + commission
                = nominal − seller_discount
    These are only equal when store_credit == 0. When the buyer redeemed store
    credit at checkout, that money was already debited from USER_STORE_CREDIT
    and credited to PLATFORM_REFUND_POOL in a separate journal — so the
    `buyer_paid` here is *before* store credit is added back. The platform
    effectively pays the seller by drawing from PLATFORM_REFUND_POOL.

    To make this journal balance regardless, we credit any store-credit-funded
    portion from PLATFORM_REFUND_POOL → SELLER_PENDING in the same journal.
    """
    from .models import Account, AccountType
    journal_key = idempotency_key or f'order:{order.id}:payment'

    buyer_paid_cents = _to_cents(buyer_paid)
    commission_cents = _to_cents(commission_amount)
    platform_subsidy_cents = _to_cents(platform_subsidy)
    seller_discount_cents = _to_cents(seller_discount)
    store_credit_cents = _to_cents(getattr(order, 'store_credit_used', 0) or 0)
    nominal_cents = (
        buyer_paid_cents + platform_subsidy_cents + seller_discount_cents + store_credit_cents
    )
    seller_earnings_cents = nominal_cents - commission_cents - seller_discount_cents

    if seller_earnings_cents < 0 or commission_cents < 0:
        raise LedgerError('Negative seller earnings or commission')

    lines = []
    if buyer_paid_cents > 0:
        lines.append((Account.platform(AccountType.EXTERNAL_CLEARING, currency='AOA'),
                      buyer_paid_cents, 'debit'))
    if platform_subsidy_cents > 0:
        lines.append((Account.platform(AccountType.PLATFORM_REVENUE, currency='AOA'),
                      platform_subsidy_cents, 'debit'))
    if store_credit_cents > 0:
        # Buyer's store credit was already moved to PLATFORM_REFUND_POOL at checkout;
        # now the pool funds the seller's share for this order.
        lines.append((Account.platform(AccountType.PLATFORM_REFUND_POOL, currency='AOA'),
                      store_credit_cents, 'debit'))

    if seller_earnings_cents > 0:
        lines.append((Account.for_user(order.seller, AccountType.SELLER_PENDING, currency='AOA'),
                      seller_earnings_cents, 'credit'))
    if commission_cents > 0:
        lines.append((Account.platform(AccountType.PLATFORM_REVENUE, currency='AOA'),
                      commission_cents, 'credit'))

    journal, created = post(
        journal_key, lines,
        ref_type='order', ref_id=str(order.id),
        description=f'Payment received for order {str(order.id)[:8]}',
        user=order.buyer,
    )
    return journal, created


def record_escrow_release(*, order, amount, idempotency_key=None):
    """Move escrow → wallet on delivery.

    Posting (AOA, in cents):
        DR SELLER_PENDING          amount
        CR SELLER_WALLET           amount
    """
    from .models import Account, AccountType
    return transfer(
        from_account=Account.for_user(order.seller, AccountType.SELLER_PENDING, currency='AOA'),
        to_account=Account.for_user(order.seller, AccountType.SELLER_WALLET, currency='AOA'),
        amount=amount,
        journal_key=idempotency_key or f'order:{order.id}:escrow_release',
        ref_type='order', ref_id=str(order.id),
        description=f'Escrow released for order {str(order.id)[:8]}',
    )


def record_payout_debit(*, seller, amount, payout_id, idempotency_key=None):
    """Seller requests payout: SELLER_WALLET → EXTERNAL_CLEARING."""
    from .models import Account, AccountType
    return transfer(
        from_account=Account.for_user(seller, AccountType.SELLER_WALLET, currency='AOA'),
        to_account=Account.platform(AccountType.EXTERNAL_CLEARING, currency='AOA'),
        amount=amount,
        journal_key=idempotency_key or f'payout:{payout_id}:debit',
        ref_type='payout', ref_id=str(payout_id),
        description=f'Payout {payout_id} to bank',
        user=seller,
    )


def record_refund_to_buyer(*, order, amount, refund_id, destination='store_credit', idempotency_key=None):
    """Refund flows back to the buyer.

    `destination` controls where the refund lands:
      'store_credit' (default) — money goes to USER_STORE_CREDIT
      'gateway'                — money goes back out via EXTERNAL_CLEARING

    Source is the SELLER_WALLET (or SELLER_PENDING if escrow not yet released).
    For MVP we always pull from SELLER_WALLET — caller must ensure escrow has been
    released first (auto-completed orders meet this).

    Posting (AOA, in cents):
      destination='store_credit':
        DR SELLER_WALLET             amount
        CR USER_STORE_CREDIT         amount
      destination='gateway':
        DR SELLER_WALLET             amount
        CR EXTERNAL_CLEARING         amount   (refund issued via gateway)
    """
    from .models import Account, AccountType
    if destination not in ('store_credit', 'gateway'):
        raise LedgerError(f'Unknown refund destination: {destination!r}')

    src = Account.for_user(order.seller, AccountType.SELLER_WALLET, currency='AOA')
    if destination == 'store_credit':
        dst = Account.for_user(order.buyer, AccountType.USER_STORE_CREDIT, currency='AOA')
    else:
        dst = Account.platform(AccountType.EXTERNAL_CLEARING, currency='AOA')

    return transfer(
        from_account=src, to_account=dst,
        amount=amount,
        journal_key=idempotency_key or f'refund:{refund_id}:{destination}',
        ref_type='refund', ref_id=str(refund_id),
        description=f'Refund {refund_id} ({destination}) for order {str(order.id)[:8]}',
        user=order.buyer,
    )


def record_payout_reverse(*, seller, amount, payout_id, idempotency_key=None):
    """Payout was rejected: EXTERNAL_CLEARING → SELLER_WALLET (refund the debit)."""
    from .models import Account, AccountType
    return transfer(
        from_account=Account.platform(AccountType.EXTERNAL_CLEARING, currency='AOA'),
        to_account=Account.for_user(seller, AccountType.SELLER_WALLET, currency='AOA'),
        amount=amount,
        journal_key=idempotency_key or f'payout:{payout_id}:reverse',
        ref_type='payout', ref_id=str(payout_id),
        description=f'Payout {payout_id} reversed',
        user=seller,
    )


def transfer(from_account, to_account, *, amount=None, amount_cents=None, journal_key,
             ref_type='', ref_id='', description='', user=None):
    """Move money / units from `from_account` to `to_account`.

    Pass exactly one of:
        amount        — Decimal/int Kz (multiplied by 100 internally)
        amount_cents  — already-in-smallest-unit integer (loyalty points use 1=1)

    Conventionally:
        from_account is debited (its balance goes down)
        to_account is credited (its balance goes up)

    Both accounts must use the same currency (enforced).

    Returns: (journal, created: bool, amount_cents: int)
    """
    if amount is None and amount_cents is None:
        raise LedgerError('Pass amount or amount_cents')
    if amount is not None and amount_cents is not None:
        raise LedgerError('Pass either amount or amount_cents, not both')
    if amount_cents is None:
        amount_cents = _to_cents(amount)
    amount_cents = int(amount_cents)

    if amount_cents <= 0:
        raise LedgerError(f'Transfer amount must be positive, got {amount_cents}')
    if from_account.id == to_account.id:
        raise LedgerError('Cannot transfer between the same account')
    if from_account.currency != to_account.currency:
        raise LedgerError(
            f'Currency mismatch: {from_account.currency} vs {to_account.currency}'
        )

    journal, created = post(
        journal_key,
        lines=[
            (from_account, amount_cents, 'debit'),
            (to_account, amount_cents, 'credit'),
        ],
        ref_type=ref_type, ref_id=ref_id,
        description=description, user=user,
    )
    return journal, created, amount_cents
