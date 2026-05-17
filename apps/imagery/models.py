"""
apps/imagery/models.py

Image variant pipeline. Two tables:

  ImageSource    The canonical original. Identified by SHA-256 of the bytes
                 so an upload that duplicates an existing image dedupes to
                 the same row — no wasted storage.

  ImageVariant   A derived size+format. (source, variant, format) is unique;
                 lazy-generated on first request, durable thereafter.

Lifecycle:
  Seller uploads photo → register_upload() hashes the bytes, dedupes,
    creates ImageSource (PENDING) + outbox event 'image.uploaded'.
  Background task generate_variants_for_source() makes:
    • thumb (96x96, center-crop, JPEG q=80) — for grid views
    • sm    (320 wide, JPEG q=85)           — mobile detail
    • md    (640 wide, JPEG q=85)           — desktop detail
    • lg    (1280 wide, JPEG q=82)          — full screen
  Plus WebP versions of sm/md/lg for clients that accept it (50% smaller).

Bandwidth math: 5MB phone photo → 4 variants × 2 formats × ~80KB =
~640KB total, served via responsive <picture>. Mobile clients pull
maybe one 80KB sm.webp. 60x bandwidth reduction on the hot path.
"""
import hashlib
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


# Variant size definitions. Keeping these in the model file (not just
# the service) so they're visible in admin listings and easy to add to.
VARIANT_SIZES = {
    # name → (max_width, max_height, crop_square, jpeg_quality)
    'thumb': (96, 96, True, 80),
    'sm':    (320, None, False, 85),
    'md':    (640, None, False, 85),
    'lg':    (1280, None, False, 82),
}

# Formats we emit. JPEG is the universal compatibility baseline; WebP
# yields ~25-35% smaller files for clients that advertise it.
VARIANT_FORMATS = ('jpeg', 'webp')


class SourceStatus(models.TextChoices):
    PENDING   = 'pending',   'Pending generation'
    READY     = 'ready',     'All variants generated'
    PARTIAL   = 'partial',   'Some variants generated, some failed'
    FAILED    = 'failed',    'Could not generate (corrupt source?)'
    DELETED   = 'deleted',   'Soft-deleted'


class ImageSource(models.Model):
    """The canonical original. SHA-256 of bytes is the natural key — two
    sellers uploading the same image deduplicate to one ImageSource."""
    # 64-char hex sha256 of the raw bytes
    sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    # Where the original lives — relative path under MEDIA_ROOT, or an
    # absolute external URL (for already-CDN-hosted source images).
    original_path = models.CharField(max_length=500)
    content_type = models.CharField(max_length=40, default='image/jpeg')
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    bytes_size = models.PositiveBigIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    status = models.CharField(
        max_length=10, choices=SourceStatus.choices,
        default=SourceStatus.PENDING, db_index=True,
    )
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class ImageVariant(models.Model):
    """A derived size+format. Lazy-generated; durable once made."""
    source = models.ForeignKey(
        ImageSource, on_delete=models.CASCADE, related_name='variants',
    )
    variant = models.CharField(max_length=10)  # 'thumb' | 'sm' | 'md' | 'lg'
    format = models.CharField(max_length=8)    # 'jpeg' | 'webp'
    storage_path = models.CharField(max_length=500)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    bytes_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'variant', 'format'],
                name='uniq_source_variant_format',
            ),
        ]
        indexes = [
            models.Index(fields=['source', 'variant']),
        ]
