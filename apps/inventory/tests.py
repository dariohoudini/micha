"""
Inventory reservation tests.

Validates the variant-aware reservation primitives that ship in
apps/inventory/service.py (commits 458b8a7, etc).

Concurrency note
─────────────────
True multi-thread concurrency tests against the reserve() service
require Postgres + ``select_for_update(skip_locked=...)`` semantics.
On SQLite the writes serialise so the test effectively checks the
LOGICAL guarantee: two sequential reserve() calls on a stock-of-1
product → first succeeds, second raises InsufficientStock. The
production lock semantics catch the multi-thread race when running
against Postgres; CI in TEST_DB_POSTGRES=1 mode runs that path.
"""
from decimal import Decimal
import uuid

import pytest

from apps.inventory.models import StockReservation, ProductVariantCombo
from apps.inventory.service import (
    reserve, release_reservation, commit_reservation, sweep_expired,
    InsufficientStock, ReservationCapReached, InvalidReservationTarget,
)
from apps.products.models import Product


# ─── Helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def stock_product(product):
    """Product with quantity=5 for reservation tests."""
    product.quantity = 5
    product.save(update_fields=['quantity'])
    return product


@pytest.fixture
def variant_combo(stock_product):
    """Variant combo with quantity=3 — distinct from parent product."""
    return ProductVariantCombo.objects.create(
        product=stock_product,
        options={'Color': 'Red', 'Size': 'M'},
        price=Decimal('200.00'),
        quantity=3,
        is_active=True,
    )


# ─── Tests ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStockReservationBasics:

    def test_reserve_product_decrements_quantity(self, buyer, stock_product):
        """Basic happy path: reserve N units → product.quantity -= N."""
        before = stock_product.quantity
        res = reserve(user=buyer, product=stock_product, quantity=2)

        stock_product.refresh_from_db()
        assert stock_product.quantity == before - 2
        assert res.quantity == 2
        assert res.is_active is True

    def test_reserve_combo_decrements_combo_NOT_product(
        self, buyer, stock_product, variant_combo,
    ):
        """The MOST IMPORTANT invariant of variant-aware reservations:
        reserving a variant combo decrements ONLY the combo's quantity,
        NOT the parent product's. The original bug (pre-458b8a7) was
        the opposite — variant reservations decremented the parent
        instead, silently overselling variants."""
        product_before = stock_product.quantity
        combo_before = variant_combo.quantity

        reserve(user=buyer, variant_combo=variant_combo, quantity=1)

        stock_product.refresh_from_db()
        variant_combo.refresh_from_db()

        assert variant_combo.quantity == combo_before - 1
        assert stock_product.quantity == product_before, (
            f'PARENT PRODUCT was decremented on variant reservation. '
            f'before={product_before} after={stock_product.quantity} — '
            f'this is the original oversell bug.'
        )

    def test_reserve_exceeding_stock_raises_insufficient(
        self, buyer, stock_product,
    ):
        """Asking for more than available raises InsufficientStock
        AND does NOT decrement the product."""
        before = stock_product.quantity
        with pytest.raises(InsufficientStock):
            reserve(user=buyer, product=stock_product, quantity=999)

        stock_product.refresh_from_db()
        assert stock_product.quantity == before, (
            'product quantity changed after a FAILED reserve — '
            'the decrement must be atomic with the row create'
        )

    def test_two_sequential_reserves_on_stock_of_one(
        self, buyer, seller, stock_product,
    ):
        """The serialised analogue of the concurrent oversell race:
        stock_product has 1 unit available; two sequential reserves
        → first succeeds, second raises. On Postgres this same
        sequence under concurrent threads exhibits the same property
        because the row-level lock serialises the writers."""
        stock_product.quantity = 1
        stock_product.save(update_fields=['quantity'])

        # User A reserves → succeeds
        reserve(user=buyer, product=stock_product, quantity=1)
        stock_product.refresh_from_db()
        assert stock_product.quantity == 0

        # User B (different account) tries → InsufficientStock
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_b = User.objects.create_user(
            email=f'b2-{uuid.uuid4().hex[:8]}@x.com',
            password='Test!2345xyz',
            is_email_verified=True,
            status='active',
        )

        with pytest.raises(InsufficientStock):
            reserve(user=user_b, product=stock_product, quantity=1)

        stock_product.refresh_from_db()
        assert stock_product.quantity == 0, (
            'second reserve must NOT have decremented further; the '
            'lock + check should have caught the over-reserve'
        )


@pytest.mark.django_db
class TestReservationConstraints:

    def test_neither_product_nor_combo_rejected(self, buyer):
        """The CHECK constraint + service-layer guard: exactly one of
        (product, variant_combo) must be set."""
        with pytest.raises(InvalidReservationTarget):
            reserve(user=buyer, quantity=1)

    def test_both_product_and_combo_rejected(
        self, buyer, stock_product, variant_combo,
    ):
        with pytest.raises(InvalidReservationTarget):
            reserve(
                user=buyer,
                product=stock_product,
                variant_combo=variant_combo,
                quantity=1,
            )

    def test_zero_quantity_rejected(self, buyer, stock_product):
        with pytest.raises(InvalidReservationTarget):
            reserve(user=buyer, product=stock_product, quantity=0)

    def test_per_user_cap_enforced(self, buyer, stock_product):
        """A single user can hold at most MAX_ACTIVE_RESERVATIONS_PER_USER.
        Without this cap, a script could spam reserve() and starve
        inventory until expiry sweeps run."""
        # Lower the cap for the test by ATTRIBUTE override to avoid the
        # slow loop creating 20 reservations.
        stock_product.quantity = 100
        stock_product.save(update_fields=['quantity'])
        original_cap = StockReservation.MAX_ACTIVE_RESERVATIONS_PER_USER
        try:
            StockReservation.MAX_ACTIVE_RESERVATIONS_PER_USER = 3
            # Fill the cap
            for _ in range(3):
                reserve(user=buyer, product=stock_product, quantity=1)
            # Next reserve should fail
            with pytest.raises(ReservationCapReached):
                reserve(user=buyer, product=stock_product, quantity=1)
        finally:
            StockReservation.MAX_ACTIVE_RESERVATIONS_PER_USER = original_cap


@pytest.mark.django_db
class TestIdempotencyKey:

    def test_same_idempotency_key_returns_existing(self, buyer, stock_product):
        """Same key + same target + same quantity → same row, no
        double decrement. Protects against retries on flaky network."""
        key = f'idem-{uuid.uuid4().hex}'
        before = stock_product.quantity

        first = reserve(
            user=buyer, product=stock_product,
            quantity=2, idempotency_key=key,
        )
        second = reserve(
            user=buyer, product=stock_product,
            quantity=2, idempotency_key=key,
        )

        assert first.id == second.id, (
            'idempotent retry created a NEW reservation — '
            'double-decrement risk in production'
        )
        stock_product.refresh_from_db()
        assert stock_product.quantity == before - 2, (
            f'quantity decremented twice (got -{before - stock_product.quantity})'
        )

    def test_same_key_different_target_rejected(
        self, buyer, stock_product,
    ):
        """Same key + DIFFERENT target = client bug. Refuse rather
        than silently decrement the wrong thing."""
        key = f'idem-{uuid.uuid4().hex}'
        # Use a DIFFERENT product for the second call
        product2 = Product.objects.create(
            store=stock_product.store,
            title='other', slug=f'other-{uuid.uuid4().hex[:6]}',
            description='', price=Decimal('100'), quantity=10,
            category=stock_product.category, is_active=True,
        )

        reserve(user=buyer, product=stock_product, quantity=1, idempotency_key=key)

        with pytest.raises(InvalidReservationTarget):
            reserve(user=buyer, product=product2, quantity=1, idempotency_key=key)


@pytest.mark.django_db
class TestReservationLifecycle:

    def test_release_restores_quantity(self, buyer, stock_product):
        before = stock_product.quantity
        res = reserve(user=buyer, product=stock_product, quantity=2)

        released = release_reservation(res)
        assert released is True

        stock_product.refresh_from_db()
        assert stock_product.quantity == before, (
            'release did not restore quantity'
        )
        res.refresh_from_db()
        assert res.is_active is False

    def test_release_is_idempotent(self, buyer, stock_product):
        """Calling release on an already-released reservation is a
        no-op (returns False)."""
        res = reserve(user=buyer, product=stock_product, quantity=1)
        release_reservation(res)
        result = release_reservation(res)
        assert result is False

    def test_commit_does_NOT_restore_stock(self, buyer, stock_product):
        """A committed reservation = a fulfilled order. The stock was
        already decremented; commit drops the reservation row but
        keeps the decrement (the buyer is taking those units away)."""
        before = stock_product.quantity
        res = reserve(user=buyer, product=stock_product, quantity=2)

        commit_reservation(res)

        stock_product.refresh_from_db()
        res.refresh_from_db()

        assert stock_product.quantity == before - 2, (
            'commit must NOT restore stock — the buyer paid for those '
            'units; restoring would oversell.'
        )
        assert res.is_active is False

    def test_sweep_expired_releases_only_expired(
        self, buyer, stock_product,
    ):
        """sweep_expired releases reservations past their expires_at;
        leaves fresh ones alone."""
        from django.utils import timezone
        from datetime import timedelta

        before = stock_product.quantity

        fresh = reserve(user=buyer, product=stock_product, quantity=1)
        old = reserve(user=buyer, product=stock_product, quantity=1)
        # Backdate the second one to "expired"
        StockReservation.objects.filter(pk=old.pk).update(
            expires_at=timezone.now() - timedelta(seconds=5),
        )

        released_count = sweep_expired()

        stock_product.refresh_from_db()
        # Fresh reservation still holds 1; old released 1 → product
        # quantity should be before - 1 (only one still reserved).
        assert stock_product.quantity == before - 1
        assert released_count >= 1

        old.refresh_from_db()
        fresh.refresh_from_db()
        assert old.is_active is False, 'expired reservation should be released'
        assert fresh.is_active is True, 'fresh reservation should NOT be released'
