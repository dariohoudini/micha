"""
Reconciliation: prove the ledger invariant `Σ (credits − debits) = 0` per currency,
and refresh each account's `cached_balance_cents` for fast reads.

Usage:
    python manage.py reconcile_ledger             # check + refresh cache
    python manage.py reconcile_ledger --check     # check only, no writes
    python manage.py reconcile_ledger --quiet     # only print on failure (cron mode)
"""
from collections import defaultdict
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from apps.ledger.models import Account, LedgerEntry


class Command(BaseCommand):
    help = 'Reconcile the ledger: verify Σ debits = Σ credits per currency; refresh cached balances.'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true',
                            help='Only verify; do not write cached balances.')
        parser.add_argument('--quiet', action='store_true',
                            help='Suppress success output (cron mode).')

    def handle(self, *args, **options):
        check_only = options['check']
        quiet = options['quiet']

        # Per-currency invariant
        per_currency = defaultdict(lambda: {'debit': 0, 'credit': 0})
        rows = (
            LedgerEntry.objects
            .values('account__currency')
            .annotate(d=Sum('debit_cents'), c=Sum('credit_cents'))
        )
        for row in rows:
            cur = row['account__currency']
            per_currency[cur]['debit'] = row['d'] or 0
            per_currency[cur]['credit'] = row['c'] or 0

        any_failure = False
        for cur, totals in per_currency.items():
            diff = totals['credit'] - totals['debit']
            if diff != 0:
                any_failure = True
                self.stderr.write(self.style.ERROR(
                    f'❌ {cur}: imbalance of {diff} cents '
                    f'(credits={totals["credit"]}, debits={totals["debit"]})'
                ))
            elif not quiet:
                self.stdout.write(self.style.SUCCESS(
                    f'✓ {cur}: balanced ({totals["credit"]} cents both sides)'
                ))

        if any_failure:
            self.stderr.write(self.style.ERROR(
                'Ledger imbalance detected. Investigate journals near the discrepancy.'
            ))
            raise SystemExit(1)

        if check_only:
            if not quiet:
                self.stdout.write(self.style.SUCCESS('Check-only mode: cached balances NOT refreshed.'))
            return

        # Refresh per-account cached balances
        updated = 0
        now = timezone.now()
        for account in Account.objects.all():
            balance = account.balance()
            if balance != account.cached_balance_cents:
                account.cached_balance_cents = balance
                account.cached_balance_at = now
                account.save(update_fields=['cached_balance_cents', 'cached_balance_at', 'updated_at'])
                updated += 1

        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f'✓ Refreshed cached balance on {updated} account(s).'
            ))

        # Spot-check: cached counter on User model vs ledger (warns only, doesn't fail)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        from apps.ledger.models import AccountType
        warnings = 0
        for acc in Account.objects.filter(type=AccountType.USER_LOYALTY_POINTS).select_related('user'):
            if not acc.user_id:
                continue
            ledger_pts = acc.cached_balance_cents
            cached_pts = acc.user.loyalty_points or 0
            if ledger_pts != cached_pts:
                warnings += 1
                self.stdout.write(self.style.WARNING(
                    f'⚠ user={acc.user_id}: User.loyalty_points={cached_pts} '
                    f'but ledger says {ledger_pts}'
                ))
        if warnings and not quiet:
            self.stdout.write(self.style.WARNING(
                f'{warnings} drift(s) between User.loyalty_points and ledger. '
                f'These are pre-ledger writes; not a current correctness bug.'
            ))
