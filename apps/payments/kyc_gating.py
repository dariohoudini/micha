"""
apps/payments/kyc_gating.py
────────────────────────────

KYC-tier-based payout limits (R2).

Why this exists
───────────────
Fraudsters' favourite marketplace pattern:
  1. Create account with throwaway email
  2. List counterfeit products at low prices
  3. Collect buyer payments
  4. Request immediate full payout
  5. Disappear before disputes land

Without tier gating, step 4 succeeds before step 5's chargebacks hit
us — leaving the platform holding the bag. The card issuer reverses
the buyer's charge, our PSP debits us back, our seller wallet is
empty (already paid out), and we eat the loss.

Tier model
──────────

  Tier 1  email verified only
          - 50,000 AOA / month payout cap (~USD 60)
          - rolling 30-day window
          - blocks new sellers from instant cash-out scams

  Tier 2  email + NIF (tax ID) + government ID upload
          - 500,000 AOA / month payout cap (~USD 600)
          - typical for individual sellers operating informally

  Tier 3  Tier 2 + business registration certificate + verified address
          - unlimited monthly cap
          - typical for registered businesses (LDA, etc.)

Tier is computed from the User's existing verification flags:
  is_email_verified        → required for all tiers
  has_nif + id_verified    → Tier 2
  business_verified        → Tier 3 (when business_verified=True on User)

Settings overrides
──────────────────
  KYC_TIER1_MONTHLY_CAP_AOA   default 50000
  KYC_TIER2_MONTHLY_CAP_AOA   default 500000
  KYC_TIER3_MONTHLY_CAP_AOA   default 0  (0 = unlimited)
  KYC_GATING_ENABLED          default True

Public API
──────────

  resolve_tier(user) -> str         'tier1' | 'tier2' | 'tier3'
  monthly_cap(tier) -> Decimal       0 = unlimited
  payout_total_in_window(user) -> Decimal   sum of payouts in last 30d
  check_payout_allowed(user, amount) -> tuple[bool, str, dict]
      Returns (allowed, error_code, details_dict).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone


log = logging.getLogger('micha.kyc')


# ─── Tier resolution ──────────────────────────────────────────────────


def resolve_tier(user) -> str:
    """Map a User to their current KYC tier.

    Defensive on field presence — different User schema versions over
    the codebase's history have had different verification field names.
    Always returns at least 'tier1' for an authenticated user (we still
    rate-limit them, just at the lowest tier).
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return 'tier1'

    # Tier 3 — full business verification.
    if (
        getattr(user, 'business_verified', False)
        or getattr(user, 'is_verified_business', False)
    ):
        return 'tier3'

    # Tier 2 — Has an approved SellerVerification (BI/ID document) AND
    # is flagged as a verified seller (proxies for NIF in current schema).
    has_id = _has_approved_seller_verification(user)
    has_nif = (
        bool(getattr(user, 'nif', None))
        or getattr(user, 'is_verified_seller', False)
    )
    if has_nif and has_id:
        return 'tier2'

    return 'tier1'


def _has_approved_seller_verification(user) -> bool:
    """True iff the user has an approved SellerVerification row.

    Defensive — verification app may not be available in tests with
    --no-migrations or if the schema rolls back to a state without it.
    """
    try:
        from apps.verification.models import SellerVerification
        return SellerVerification.objects.filter(
            seller=user, status='approved',
        ).exists()
    except Exception:
        return False


# ─── Caps ─────────────────────────────────────────────────────────────


def monthly_cap(tier: str) -> Decimal:
    """Return the monthly payout cap in AOA for ``tier``.

    0 means unlimited. Negative result coerced to 0 (safety).
    """
    defaults = {
        'tier1': Decimal('50000'),
        'tier2': Decimal('500000'),
        'tier3': Decimal('0'),  # unlimited
    }
    keys = {
        'tier1': 'KYC_TIER1_MONTHLY_CAP_AOA',
        'tier2': 'KYC_TIER2_MONTHLY_CAP_AOA',
        'tier3': 'KYC_TIER3_MONTHLY_CAP_AOA',
    }
    key = keys.get(tier)
    if not key:
        return defaults.get(tier, Decimal('50000'))
    raw = getattr(settings, key, defaults.get(tier))
    try:
        cap = Decimal(str(raw))
    except Exception:
        cap = defaults.get(tier, Decimal('50000'))
    return cap if cap >= 0 else Decimal('0')


def payout_total_in_window(user, *, days: int = 30) -> Decimal:
    """Sum of approved/processed payouts for ``user`` in the last
    ``days`` days. Includes 'pending' to prevent fraudster from
    queueing multiple simultaneous requests to bypass the cap."""
    try:
        from apps.payments.models import PayoutRequest
        since = timezone.now() - timedelta(days=days)
        total = (
            PayoutRequest.objects
            .filter(seller=user, created_at__gte=since)
            .exclude(status__in=('rejected', 'cancelled', 'failed'))
            .aggregate(models_sum=_sum('amount'))
            .get('models_sum')
        )
        return Decimal(str(total)) if total else Decimal('0')
    except Exception:
        log.exception('kyc: payout window aggregate failed')
        return Decimal('0')


def _sum(field):
    from django.db.models import Sum
    return Sum(field)


# ─── Public: gating check ─────────────────────────────────────────────


def _enabled() -> bool:
    return bool(getattr(settings, 'KYC_GATING_ENABLED', True))


def check_payout_allowed(user, amount: Decimal) -> tuple:
    """Decide whether ``user`` is allowed to request a payout of ``amount``.

    Returns (allowed: bool, error_code: str, details: dict).

      allowed=True  → details contains {'tier', 'cap', 'used', 'remaining'}
      allowed=False → error_code is one of:
                        'kyc_tier_cap_exceeded'
                        'kyc_email_unverified'
                        'kyc_disabled' (returned only when ENABLED is False
                                        AND we're noting the bypass)

    NEVER raises. Callers should refuse payouts on allowed=False with
    HTTP 403 + an actionable error message ("verify your NIF to unlock
    larger payouts").
    """
    if not _enabled():
        return True, '', {'tier': resolve_tier(user), 'gating': 'disabled'}

    # Email verification is a hard floor — without it, even Tier 1
    # payouts shouldn't fire.
    if not getattr(user, 'is_email_verified', False):
        return False, 'kyc_email_unverified', {
            'tier': 'unverified',
            'message': 'Verify your email before requesting payouts.',
        }

    tier = resolve_tier(user)
    cap = monthly_cap(tier)

    # Tier 3 (cap=0) = unlimited.
    if cap == 0:
        return True, '', {
            'tier': tier, 'cap': 'unlimited',
            'used': str(payout_total_in_window(user)),
        }

    used = payout_total_in_window(user)
    remaining = cap - used
    if (used + Decimal(str(amount))) > cap:
        return False, 'kyc_tier_cap_exceeded', {
            'tier': tier,
            'cap': str(cap),
            'used': str(used),
            'remaining': str(remaining if remaining > 0 else Decimal('0')),
            'requested': str(amount),
            'message': (
                f'Monthly payout cap for {tier} is {cap} AOA. '
                f'Already used: {used}. '
                f'Upgrade verification to increase your limit.'
            ),
        }

    return True, '', {
        'tier': tier,
        'cap': str(cap),
        'used': str(used),
        'remaining': str(remaining),
    }
