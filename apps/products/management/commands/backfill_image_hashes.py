"""
Compute Product.image_hash for products that don't have one yet.

Reads the first ProductImage of each ungrouped product, computes the
dHash, persists. Idempotent — products with image_hash already set are
skipped (use --force to recompute).

Usage:
    python manage.py backfill_image_hashes
    python manage.py backfill_image_hashes --force      # overwrite existing
    python manage.py backfill_image_hashes --batch=200
"""
from django.core.management.base import BaseCommand

from apps.products.models import Product
from apps.products.perceptual_hash import compute_dhash


class Command(BaseCommand):
    help = "Compute perceptual hashes for products that have a primary image but no image_hash."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Overwrite existing image_hash values.')
        parser.add_argument('--batch', type=int, default=500)

    def handle(self, *args, **options):
        force = options['force']
        batch = options['batch']

        qs = Product.objects.exclude(images__isnull=True)
        if not force:
            qs = qs.filter(image_hash='')
        qs = qs.distinct().prefetch_related('images').only('id', 'image_hash')

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No products need image hashing.'))
            return

        self.stdout.write(f'Computing hash for {total} product(s)…')
        ok = 0
        skipped = 0
        for product in qs.iterator(chunk_size=batch):
            img = product.images.first()
            if not img or not img.image:
                skipped += 1
                continue
            try:
                # Open the file via Django storage so this works on both
                # local FS and S3-backed deployments.
                with img.image.open('rb') as fh:
                    phash = compute_dhash(fh)
            except Exception:
                phash = None
            if not phash:
                skipped += 1
                continue
            Product.objects.filter(pk=product.pk).update(image_hash=phash)
            ok += 1
            if ok % batch == 0:
                self.stdout.write(f'  hashed {ok}…')

        self.stdout.write(self.style.SUCCESS(
            f'Hashed {ok} product(s); skipped {skipped} (no image / hash failed).'
        ))
