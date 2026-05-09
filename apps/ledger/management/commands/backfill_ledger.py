"""
One-shot backfill: post opening-balance journals reflecting existing
in-place balances on User.loyalty_points / User.store_credit /
SellerWallet.balance / SellerWallet.pending_balance, so the ledger
matches the cached counters.

After backfill, `reconcile_ledger` should still pass and
User.loyalty_points should equal `Account.for_user(...).balance()`.

Idempotent — re-running is a no-op (each opening-balance journal has
a deterministic key per account).

Usage:
    python manage.py backfill_ledger          # apply
    python manage.py backfill_ledger --dry    # preview only
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ledger.models import Account, AccountType
from apps.ledger.service import post

User = get_user_model()


class Command(BaseCommand):
    help = 'Backfill the ledger from existing in-place balance columns. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--dry', action='store_true', help='Preview only.')

    def handle(self, *args, **options):
        dry = options['dry']
        posted = 0
        skipped = 0

        # ── Loyalty points (PTS) ─────────────────────────────────────────
        loyalty_fund = None if dry else Account.platform(
            AccountType.PLATFORM_LOYALTY_FUND, currency='PTS'
        )
        for user in User.objects.filter(loyalty_points__gt=0).iterator():
            pts = int(user.loyalty_points or 0)
            if pts <= 0:
                continue
            key = f'opening:user:{user.id}:loyalty_points'
            if dry:
                self.stdout.write(f'  WOULD post {pts} pts → user {user.id}')
                posted += 1
                continue
            user_acc = Account.for_user(user, AccountType.USER_LOYALTY_POINTS, currency='PTS')
            j, created = post(
                key,
                lines=[
                    (loyalty_fund, pts, 'debit'),
                    (user_acc, pts, 'credit'),
                ],
                ref_type='opening_balance', ref_id=str(user.id),
                description=f'Opening loyalty balance for user {user.id}',
            )
            if created:
                posted += 1
            else:
                skipped += 1

        # ── Store credit (AOA) ───────────────────────────────────────────
        refund_pool = None if dry else Account.platform(
            AccountType.PLATFORM_REFUND_POOL, currency='AOA'
        )
        for user in User.objects.filter(store_credit__gt=0).iterator():
            credit = Decimal(str(user.store_credit or 0))
            if credit <= 0:
                continue
            credit_cents = int((credit * 100).to_integral_value())
            key = f'opening:user:{user.id}:store_credit'
            if dry:
                self.stdout.write(f'  WOULD post {credit} AOA store credit → user {user.id}')
                posted += 1
                continue
            user_acc = Account.for_user(user, AccountType.USER_STORE_CREDIT, currency='AOA')
            j, created = post(
                key,
                lines=[
                    (refund_pool, credit_cents, 'debit'),
                    (user_acc, credit_cents, 'credit'),
                ],
                ref_type='opening_balance', ref_id=str(user.id),
                description=f'Opening store credit for user {user.id}',
            )
            if created:
                posted += 1
            else:
                skipped += 1

        # ── Seller wallets (AOA) ─────────────────────────────────────────
        try:
            from apps.payments.models import SellerWallet
        except Exception:
            SellerWallet = None

        external_clearing = None if dry else Account.platform(
            AccountType.EXTERNAL_CLEARING, currency='AOA'
        )

        if SellerWallet is not None:
            for wallet in SellerWallet.objects.filter(balance__gt=0).select_related('seller').iterator():
                bal = Decimal(str(wallet.balance or 0))
                if bal <= 0:
                    continue
                bal_cents = int((bal * 100).to_integral_value())
                key = f'opening:wallet:{wallet.id}:balance'
                if dry:
                    self.stdout.write(f'  WOULD post {bal} AOA wallet → seller {wallet.seller_id}')
                    posted += 1
                    continue
                seller_acc = Account.for_user(wallet.seller, AccountType.SELLER_WALLET, currency='AOA')
                j, created = post(
                    key,
                    lines=[
                        (external_clearing, bal_cents, 'debit'),
                        (seller_acc, bal_cents, 'credit'),
                    ],
                    ref_type='opening_balance', ref_id=str(wallet.id),
                    description=f'Opening wallet for seller {wallet.seller_id}',
                )
                if created:
                    posted += 1
                else:
                    skipped += 1

            for wallet in SellerWallet.objects.filter(pending_balance__gt=0).select_related('seller').iterator():
                pending = Decimal(str(wallet.pending_balance or 0))
                if pending <= 0:
                    continue
                pending_cents = int((pending * 100).to_integral_value())
                key = f'opening:wallet:{wallet.id}:pending'
                if dry:
                    self.stdout.write(f'  WOULD post {pending} AOA pending → seller {wallet.seller_id}')
                    posted += 1
                    continue
                pending_acc = Account.for_user(wallet.seller, AccountType.SELLER_PENDING, currency='AOA')
                j, created = post(
                    key,
                    lines=[
                        (external_clearing, pending_cents, 'debit'),
                        (pending_acc, pending_cents, 'credit'),
                    ],
                    ref_type='opening_balance', ref_id=str(wallet.id),
                    description=f'Opening pending balance for seller {wallet.seller_id}',
                )
                if created:
                    posted += 1
                else:
                    skipped += 1

        if dry:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN: would post {posted} journal(s).'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Backfill complete: posted={posted}, already-present={skipped}.'
            ))
            self.stdout.write('Run `python manage.py reconcile_ledger` to verify.')
