"""
Assign Product.product_group for every existing product whose group is null.

The pre_save signal handles new products, but rows created before the
signal landed (or with the signal disabled) need a one-shot pass.

Idempotent — re-running is a no-op (existing rows already have a group).

Usage:
    python manage.py backfill_product_groups
    python manage.py backfill_product_groups --dry
"""
from django.core.management.base import BaseCommand

from apps.products.models import Product, ProductGroup


class Command(BaseCommand):
    help = 'Backfill Product.product_group for legacy rows.'

    def add_arguments(self, parser):
        parser.add_argument('--dry', action='store_true', help='Preview only.')

    def handle(self, *args, **options):
        dry = options['dry']
        qs = Product.objects.filter(product_group__isnull=True).select_related('category')
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No products need a group. Done.'))
            return

        self.stdout.write(f'Found {total} ungrouped product(s).')
        assigned = 0
        for product in qs.iterator(chunk_size=500):
            group, created = ProductGroup.find_or_create(
                title=product.title or '',
                brand=product.brand or '',
                category=product.category,
            )
            if dry:
                self.stdout.write(
                    f'  WOULD assign product {product.id} → group {group.id} ({"new" if created else "existing"})'
                )
                assigned += 1
                continue
            Product.objects.filter(pk=product.pk).update(product_group=group)
            assigned += 1

        if dry:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN: would group {assigned} product(s).'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Grouped {assigned} product(s).'))
