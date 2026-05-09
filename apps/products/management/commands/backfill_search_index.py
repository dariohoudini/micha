"""
Backfill `Product.search_vector` for all rows.

Run once after deploying the search-vector migration. New rows are
auto-indexed via the post_save signal — only legacy rows need this.

Usage:
    python manage.py backfill_search_index           # all products
    python manage.py backfill_search_index --batch=500
"""
from django.core.management.base import BaseCommand
from django.db import connection

from apps.products.models import Product
from apps.products.search import update_search_vector


class Command(BaseCommand):
    help = 'Recompute search_vector for all products.'

    def add_arguments(self, parser):
        parser.add_argument('--batch', type=int, default=500)

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            self.stdout.write(self.style.WARNING(
                'Not running on Postgres; search_vector is unused. Skipping.'
            ))
            return

        batch = options['batch']
        qs = Product.objects.select_related('category').prefetch_related('tags').only(
            'id', 'title', 'brand', 'description', 'category__name',
        )

        total = 0
        for product in qs.iterator(chunk_size=batch):
            update_search_vector(product)
            total += 1
            if total % batch == 0:
                self.stdout.write(f'  indexed {total}…')

        self.stdout.write(self.style.SUCCESS(f'Indexed {total} product(s).'))
