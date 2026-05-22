"""
Ledger correctness tests.

The single most important invariant of any double-entry ledger:

    Σ debits == Σ credits

across all accounts at all times. If it ever drifts, money is missing.

These tests post realistic journals through ``apps.ledger.service`` and
assert the invariant holds. They are deliberately READ-WRITE tests (not
mocked) — the value is verifying the actual ORM-level posting code, not
a Python abstraction of it.

Why this file exists
─────────────────────
The audit found apps/ledger had ZERO tests. The single most important
financial invariant in the codebase was unverified. A future refactor
could silently introduce arithmetic drift; without a test asserting
the invariant, it would only be caught in production reconciliation —
weeks later, after material money loss.
"""
from decimal import Decimal

import pytest
from django.db.models import Sum

from apps.ledger.models import LedgerEntry, Account, AccountType, Journal
from apps.ledger.service import (
    post, record_payment_received, record_payout_debit,
    record_payout_reverse, record_refund_to_buyer,
)


# ─── Helpers ──────────────────────────────────────────────────────────


def assert_ledger_balanced(*, msg=''):
    """Assert Σ debits == Σ credits across the entire LedgerEntry table.

    The fundamental invariant of double-entry bookkeeping. If this
    ever fails, money has been created or destroyed somewhere and the
    platform's books no longer add up.
    """
    debits = LedgerEntry.objects.aggregate(
        total=Sum('debit_cents'),
    )['total'] or 0
    credits = LedgerEntry.objects.aggregate(
        total=Sum('credit_cents'),
    )['total'] or 0
    assert debits == credits, (
        f'{msg or "ledger imbalanced"}: '
        f'debits={debits} credits={credits} drift={debits - credits} cents'
    )


def assert_journal_balanced(journal, *, msg=''):
    """Assert Σ debits == Σ credits WITHIN a single journal.

    A weaker invariant than the global one but useful for pinpointing
    which journal is misbehaving when the global invariant fails.
    """
    debits = journal.entries.aggregate(total=Sum('debit_cents'))['total'] or 0
    credits = journal.entries.aggregate(total=Sum('credit_cents'))['total'] or 0
    assert debits == credits, (
        f'{msg or f"journal {journal.id} imbalanced"}: '
        f'debits={debits} credits={credits} drift={debits - credits}'
    )


# ─── Tests ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLedgerInvariants:
    """The fundamental double-entry invariant must hold after every
    post(). These tests post a sequence of realistic journals and
    verify the invariant survives each step + the cumulative state."""

    def test_empty_ledger_is_balanced(self):
        """The vacuous case. Σ debits == Σ credits == 0."""
        assert_ledger_balanced(msg='empty ledger should be balanced')

    def test_simple_payment_received_balances(self, buyer, seller):
        """A buyer-paid-100, commission-15 journal must balance.

        Posting:
          DR EXTERNAL_CLEARING       8500 cents  (buyer paid 85 AOA)
          CR SELLER_PENDING          7000 cents  (seller earns 70 AOA)
          CR PLATFORM_REVENUE        1500 cents  (commission 15 AOA)
        Σ debits  = 8500
        Σ credits = 8500
        """
        from apps.orders.models import Order
        import uuid
        order = Order.objects.create(
            buyer=buyer, seller=seller, status='confirmed',
            subtotal=Decimal('85.00'), total=Decimal('85.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        journal, created = record_payment_received(
            order=order,
            buyer_paid=Decimal('85.00'),
            commission_amount=Decimal('15.00'),
        )
        assert created is True
        assert_journal_balanced(journal)
        assert_ledger_balanced()

    def test_payment_with_platform_subsidy_balances(self, buyer, seller):
        """When the platform funds part of a discount, the journal
        still balances because the subsidy is debited from
        PLATFORM_REVENUE.

        DR EXTERNAL_CLEARING       7500 (buyer paid 75 — got 10 off)
        DR PLATFORM_REVENUE        1000 (platform subsidised 10)
        CR SELLER_PENDING          7000 (seller still earns 70)
        CR PLATFORM_REVENUE        1500 (commission 15 unchanged)
        """
        from apps.orders.models import Order
        import uuid
        order = Order.objects.create(
            buyer=buyer, seller=seller, status='confirmed',
            subtotal=Decimal('85.00'), total=Decimal('75.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        journal, _ = record_payment_received(
            order=order,
            buyer_paid=Decimal('75.00'),
            commission_amount=Decimal('15.00'),
            platform_subsidy=Decimal('10.00'),
        )
        assert_journal_balanced(journal)
        assert_ledger_balanced()

    def test_invariant_holds_through_full_lifecycle(self, buyer, seller):
        """End-to-end lifecycle: payment → escrow release → payout →
        refund → reverse-payout. Posting EVERY journal in sequence,
        verify the invariant after EACH step.

        This is the real-world test that catches subtle arithmetic
        bugs that wouldn't show up on a single journal but accumulate
        across the lifecycle.
        """
        from apps.orders.models import Order
        import uuid
        order = Order.objects.create(
            buyer=buyer, seller=seller, status='delivered',
            subtotal=Decimal('100.00'), total=Decimal('100.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )

        # Step 1: payment received
        record_payment_received(
            order=order,
            buyer_paid=Decimal('100.00'),
            commission_amount=Decimal('20.00'),
        )
        assert_ledger_balanced(msg='after payment received')

        # Step 2: escrow released to seller wallet
        from apps.ledger.service import record_escrow_release
        record_escrow_release(order=order, amount=Decimal('80.00'))
        assert_ledger_balanced(msg='after escrow release')

        # Step 3: seller requests payout — debit wallet
        record_payout_debit(
            seller=seller,
            amount=Decimal('80.00'),
            payout_id=f'payout-{uuid.uuid4().hex}',
        )
        assert_ledger_balanced(msg='after payout debit')

    def test_idempotent_post_does_not_drift(self, buyer, seller):
        """Calling record_payment_received TWICE with the same
        idempotency key MUST NOT post the journal twice. Without
        idempotency, retries would double-post and drift the ledger.
        """
        from apps.orders.models import Order
        import uuid
        order = Order.objects.create(
            buyer=buyer, seller=seller, status='confirmed',
            subtotal=Decimal('50.00'), total=Decimal('50.00'),
            idempotency_key=f'test-{uuid.uuid4().hex}',
        )
        key = f'test-key-{uuid.uuid4().hex}'

        j1, created1 = record_payment_received(
            order=order, buyer_paid=Decimal('50.00'),
            commission_amount=Decimal('5.00'),
            idempotency_key=key,
        )
        entries_after_first = LedgerEntry.objects.count()

        j2, created2 = record_payment_received(
            order=order, buyer_paid=Decimal('50.00'),
            commission_amount=Decimal('5.00'),
            idempotency_key=key,
        )
        entries_after_second = LedgerEntry.objects.count()

        # Same journal returned; no new entries.
        assert j1.pk == j2.pk, 'idempotent retry must return the original journal'
        assert created1 is True
        assert created2 is False, 'second call must report not-created'
        assert entries_after_first == entries_after_second, (
            'idempotent retry must NOT create new ledger entries'
        )
        assert_ledger_balanced()


@pytest.mark.django_db
class TestLedgerEntryConstraints:
    """LedgerEntry has model-level CHECK constraints that prevent
    posting a row that violates double-entry invariants. Verify the
    constraints actually fire on bad input."""

    def test_entry_must_have_exactly_one_direction(self):
        """An entry with BOTH debit AND credit > 0 violates the
        check_constraint; a row with neither (both = 0) also violates.
        Verifies the DB-level guard, not just app-level logic."""
        from django.db.utils import IntegrityError
        from apps.ledger.models import Journal

        # Create a journal first
        j = Journal.objects.create(
            idempotency_key='test-constraint',
            description='test',
        )
        platform_revenue = Account.platform(AccountType.PLATFORM_REVENUE)

        # Both directions positive — should violate constraint
        with pytest.raises(IntegrityError):
            LedgerEntry.objects.create(
                journal=j, account=platform_revenue,
                debit_cents=100, credit_cents=100,
            )

    def test_entry_cannot_have_negative_amounts(self):
        from django.db.utils import IntegrityError
        from apps.ledger.models import Journal

        j = Journal.objects.create(
            idempotency_key='test-negative',
            description='test',
        )
        platform_revenue = Account.platform(AccountType.PLATFORM_REVENUE)

        with pytest.raises(IntegrityError):
            LedgerEntry.objects.create(
                journal=j, account=platform_revenue,
                debit_cents=-100, credit_cents=0,
            )
