"""Idempotently create the first-order welcome coupon (First-Run doc CH7)."""
from django.core.management.base import BaseCommand

from apps.promotions.welcome import ensure_welcome_coupon


class Command(BaseCommand):
    help = 'Create/ensure the BEMVINDO15 welcome coupon exists.'

    def handle(self, *args, **options):
        c = ensure_welcome_coupon()
        self.stdout.write(self.style.SUCCESS(
            f'Welcome coupon ready: {c.code} ({c.discount_value}% off, '
            f'min {c.min_order_amount} Kz, cap {c.max_discount_amount} Kz)'))
