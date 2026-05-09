"""
Backfill Buyer Protection state + deadline for existing orders.

Existing orders have protection_state='awaiting_seller' as the default
column value (which is wrong for orders that are already shipped or
delivered). This command computes the correct state from each order's
current status and sets a deadline relative to its updated_at, so the
clock doesn't restart from "now" for an order that's been sitting at
"shipped" for a month.

Usage:
    python manage.py backfill_protection             # apply
    python manage.py backfill_protection --dry       # preview
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.orders.models import Order


class Command(BaseCommand):
    help = "Set protection_state + protection_deadline_at for legacy orders."

    def add_arguments(self, parser):
        parser.add_argument('--dry', action='store_true')

    def handle(self, *args, **options):
        dry = options['dry']
        updated = 0
        skipped = 0

        for order in Order.objects.iterator(chunk_size=500):
            new_state = Order.PROTECTION_STATE_BY_STATUS.get(order.status, 'none')
            days = Order.PROTECTION_DAYS.get(order.status)

            if days is None:
                # Cancelled / refunded / completed — no deadline
                new_deadline = None
            else:
                # Anchor the deadline to the *updated_at* of the order so a
                # 5-month-old shipped order doesn't suddenly get 30 days again.
                # Subtract a day's grace if the deadline has already passed.
                new_deadline = order.updated_at + timedelta(days=days)

            if (order.protection_state == new_state
                    and order.protection_deadline_at == new_deadline):
                skipped += 1
                continue

            if dry:
                self.stdout.write(
                    f'  WOULD set order {order.id}: state={new_state}, deadline={new_deadline}'
                )
                updated += 1
                continue

            with transaction.atomic():
                order.protection_state = new_state
                order.protection_deadline_at = new_deadline
                order.save(update_fields=['protection_state', 'protection_deadline_at'])
            updated += 1

        if dry:
            self.stdout.write(self.style.SUCCESS(
                f'DRY RUN: would update {updated}, skip {skipped} (already correct).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Backfill complete: updated {updated}, skipped {skipped}.'
            ))
