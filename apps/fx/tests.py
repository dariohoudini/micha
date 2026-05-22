"""
FX temporal-correctness tests.

The single most important property of the FX layer for marketplace
accounting:

    A refund issued months AFTER an order must use the rate
    that was in effect AT THE TIME OF THE ORDER, not the current
    rate. Currency moves; refunds must give back the same VALUE,
    not the same number.

Without this, a buyer who paid 100 USD when 1 USD = 500 AOA
(i.e. 50 000 AOA debited from their card) refunded 3 months later
when 1 USD = 600 AOA would get 100 USD = 60 000 AOA back —
overpaying by 10 000 AOA. Or the inverse, underpaying.

These tests verify the temporal lookup is correct.
"""
from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.fx.models import FXRate, FXRateSource
from apps.fx.service import (
    get_rate, convert, update_rate, is_rate_stale,
    FXError, FXDriftError, RateNotFound,
)


@pytest.mark.django_db
class TestFXTemporalSelection:
    """The CRITICAL property: get_rate(at=<past_timestamp>) returns
    the rate that was in effect at that timestamp, not the current
    rate."""

    def test_get_rate_at_past_timestamp_returns_historical_rate(self):
        """Pose the production scenario:
          • Day 1: USD→AOA = 500. Order placed; buyer pays 50k AOA.
          • Day 30: USD→AOA = 600 (devaluation).
          • Day 30: refund issued.

        The refund must convert at the DAY-1 rate (500), not the
        current rate (600). Otherwise the buyer gets too much or
        too little AOA back.
        """
        # Day 1: set USD→AOA = 500
        day1 = timezone.now() - timedelta(days=30)
        FXRate.objects.create(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('500.0'), source=FXRateSource.MANUAL,
            valid_from=day1, valid_until=day1 + timedelta(days=15),
        )
        # Day 15 → present: USD→AOA = 600 (current rate)
        update_rate(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('600.0'),
        )

        # Refund query: what was the rate ON DAY 1?
        day1_lookup = day1 + timedelta(hours=1)
        rate_at_day1 = get_rate('USD', 'AOA', at=day1_lookup)
        assert rate_at_day1 is not None
        assert rate_at_day1.rate == Decimal('500.0'), (
            f'BUG: refund would use {rate_at_day1.rate} instead of 500. '
            f'Temporal lookup broken — refunds compute against current '
            f'rate, not order rate.'
        )

        # Sanity: current rate is the new value
        current = get_rate('USD', 'AOA')
        assert current.rate == Decimal('600.0')

    def test_convert_with_explicit_at_uses_historical_rate(self):
        """The convert() function's `at` parameter must produce the
        amount that would have been correct AT that historical time."""
        # Day 1: 1 USD = 500 AOA
        day1 = timezone.now() - timedelta(days=10)
        FXRate.objects.create(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('500.0'), source=FXRateSource.MANUAL,
            valid_from=day1, valid_until=day1 + timedelta(days=2),
        )
        # Day 5: rate doubled
        update_rate(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('1000.0'), force=True,  # >25% drift, force
        )

        # 100 USD → AOA at day-1 rate should be 50 000
        amount_day1 = convert(
            Decimal('100'),
            from_currency='USD', to_currency='AOA',
            at=day1 + timedelta(hours=1),
            log_event=False,
        )
        assert amount_day1 == Decimal('50000.00'), (
            f'historical conversion wrong: got {amount_day1}, expected 50000'
        )

        # And the CURRENT rate would give 100 000
        amount_now = convert(
            Decimal('100'),
            from_currency='USD', to_currency='AOA',
            log_event=False,
        )
        assert amount_now == Decimal('100000.00')


@pytest.mark.django_db
class TestFXDriftGuard:
    """The fat-finger drift guard prevents catastrophic rate updates."""

    def test_large_drift_rejected_without_force(self):
        """A proposed rate that differs from current by > 25% is
        rejected — protects against typos like '0.011' typed when
        '0.0011' was meant (10× off)."""
        # Establish a current rate
        update_rate(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('500.0'),
        )
        # Attempt a 100% jump — should be rejected
        with pytest.raises(FXDriftError) as excinfo:
            update_rate(
                source_currency='USD', target_currency='AOA',
                rate=Decimal('1000.0'),
            )
        # Error carries the diagnostic data for admin UI
        err = excinfo.value
        assert err.current == Decimal('500.0')
        assert err.proposed == Decimal('1000.0')
        assert err.drift_pct > 25

        # Current rate unchanged
        current = get_rate('USD', 'AOA')
        assert current.rate == Decimal('500.0'), (
            'drift was applied despite the guard'
        )

    def test_force_true_overrides_drift_guard(self):
        """Operators explicitly override for legitimate large moves
        (AOA has had ~50% devaluations during crisis periods)."""
        update_rate(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('500.0'),
        )
        new = update_rate(
            source_currency='USD', target_currency='AOA',
            rate=Decimal('1000.0'),
            force=True,
            note='real devaluation',
        )
        assert new.rate == Decimal('1000.0')
        assert '[force]' in new.note, (
            'forced updates must be tagged in audit trail'
        )

    def test_small_drift_within_cap_allowed(self):
        """A 10% drift is well within the 25% cap and goes through."""
        update_rate(source_currency='EUR', target_currency='AOA',
                    rate=Decimal('600.0'))
        # 5% drift
        updated = update_rate(
            source_currency='EUR', target_currency='AOA',
            rate=Decimal('630.0'),
        )
        assert updated.rate == Decimal('630.0')

    def test_first_rate_for_pair_no_drift_check(self):
        """No current rate → no comparison → no drift check fires."""
        # New pair, never seen before
        update_rate(
            source_currency='ZAR', target_currency='AOA',
            rate=Decimal('45.0'),
        )
        current = get_rate('ZAR', 'AOA')
        assert current.rate == Decimal('45.0')


@pytest.mark.django_db
class TestFXBasics:

    def test_same_currency_returns_none(self):
        """USD → USD should short-circuit; callers should not invoke
        convert() for same-currency pairs."""
        assert get_rate('USD', 'USD') is None

    def test_same_currency_convert_returns_input(self):
        """convert(N, USD, USD, ...) short-circuits without needing
        an FXRate row to exist for USD→USD."""
        result = convert(
            Decimal('100'), from_currency='USD', to_currency='USD',
            log_event=False,
        )
        assert result == Decimal('100.00')

    def test_none_amount_returns_zero(self):
        """convert(None, ...) returns Decimal(0) without raising,
        even when no rate is configured for the pair."""
        assert convert(
            None, from_currency='USD', to_currency='AOA',
            log_event=False,
        ) == Decimal(0)

    def test_convert_without_rate_raises_rate_not_found(self):
        """An attempt to convert AUD→AOA when no AUD rate exists
        raises RateNotFound — caller MUST handle this explicitly,
        not silently get a wrong number."""
        with pytest.raises(RateNotFound):
            convert(
                Decimal('100'), from_currency='AUD', to_currency='AOA',
                log_event=False,
            )

    def test_negative_rate_rejected(self):
        with pytest.raises(FXError):
            update_rate(
                source_currency='USD', target_currency='AOA',
                rate=Decimal('-1'),
            )

    def test_only_one_current_rate_per_pair(self):
        """The UNIQUE-current constraint: at most one row with
        valid_until=NULL per (source, target). update_rate() closes
        the previous open row in the same atomic block."""
        update_rate(source_currency='BRL', target_currency='AOA',
                    rate=Decimal('180.0'))
        update_rate(source_currency='BRL', target_currency='AOA',
                    rate=Decimal('190.0'))
        update_rate(source_currency='BRL', target_currency='AOA',
                    rate=Decimal('200.0'))
        current_count = FXRate.objects.filter(
            source_currency='BRL', target_currency='AOA',
            valid_until__isnull=True,
        ).count()
        assert current_count == 1

    def test_is_rate_stale_detects_aged_rates(self):
        """A rate older than FX_MAX_AGE_HOURS is stale. Defaults to
        36h; we backdate a row past that and confirm detection."""
        update_rate(source_currency='CNY', target_currency='AOA',
                    rate=Decimal('130.0'))
        row = get_rate('CNY', 'AOA')
        assert is_rate_stale(row) is False

        # Backdate to 100h ago
        FXRate.objects.filter(pk=row.pk).update(
            valid_from=timezone.now() - timedelta(hours=100),
        )
        row.refresh_from_db()
        assert is_rate_stale(row) is True
