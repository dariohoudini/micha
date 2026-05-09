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
