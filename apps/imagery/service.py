"""
apps/imagery/service.py

Public entrypoints:

  register_upload(file_bytes, *, content_type, uploaded_by, storage=None)
      → ImageSource
    Hash + dedupe + persist the original; emit 'image.uploaded' outbox
    event so the background variant generator picks it up.

  generate_variants_for_source(source) -> dict
    Make every (variant × format) combination defined in
    models.VARIANT_SIZES × VARIANT_FORMATS. Idempotent — an existing
    ImageVariant row is skipped. Updates the source's status to READY /
    PARTIAL / FAILED.

  get_variant_url(source, variant, format) -> str | None
    Constant-time lookup of a known variant. Returns None if the
    variant doesn't exist yet — caller can fall back to the source URL
    or trigger generation.

Design choices:
  • Pillow does all the resizing — LANCZOS for downscale quality.
  • JPEG quality tuned per-variant size (thumb tolerates more loss).
  • WebP via Pillow's built-in plugin (fail-soft if not installed).
  • Storage is a pluggable callable so tests can use in-memory dicts
    while prod uses Django's default_storage (typically S3).
  • EXIF stripping baked in — privacy + smaller files.
"""
from __future__ import annotations
import io
import logging
from typing import Callable

from django.core.files.storage import default_storage
from django.utils import timezone

from .models import (
    ImageSource, ImageVariant, SourceStatus,
    VARIANT_SIZES, VARIANT_FORMATS,
)

log = logging.getLogger(__name__)


class ImageryError(Exception):
    pass


# ─── Storage abstraction ───────────────────────────────────────────────────

class _DefaultStorage:
    """Wraps Django's default_storage so tests can inject an in-memory
    backend without monkeypatching globals."""
    def save(self, path: str, data: bytes) -> str:
        from django.core.files.base import ContentFile
        return default_storage.save(path, ContentFile(data))

    def url(self, path: str) -> str:
        try:
            return default_storage.url(path)
        except Exception:
            return path


# ─── Register an upload ────────────────────────────────────────────────────

def register_upload(file_bytes: bytes, *, content_type: str = 'image/jpeg',
                    uploaded_by=None, storage=None) -> ImageSource:
    """Hash the bytes; dedupe to an existing ImageSource if we've seen
    them before; otherwise persist + emit an outbox event for async
    variant generation.

    Idempotent by content — same bytes uploaded twice produces the
    same ImageSource row. The 'image.uploaded' event is published only
    on the first (real) upload.
    """
    if not file_bytes:
        raise ImageryError('empty upload')
    storage = storage or _DefaultStorage()

    sha = ImageSource.hash_bytes(file_bytes)
    existing = ImageSource.objects.filter(sha256=sha).first()
    if existing is not None:
        return existing

    # Inspect dimensions via Pillow without holding the full image in memory
    # beyond what we already have.
    from PIL import Image
    try:
        with Image.open(io.BytesIO(file_bytes)) as im:
            width, height = im.size
            actual_format = (im.format or '').lower()
    except Exception as e:
        raise ImageryError(f'unreadable image: {e}')

    # Map Pillow format → content_type if caller passed a generic one
    fmt_to_ct = {'jpeg': 'image/jpeg', 'png': 'image/png',
                 'webp': 'image/webp', 'gif': 'image/gif'}
    if actual_format in fmt_to_ct:
        content_type = fmt_to_ct[actual_format]

    # Persist the original
    ext = content_type.split('/')[-1] if '/' in content_type else 'bin'
    path = f'imagery/sources/{sha[:2]}/{sha[2:4]}/{sha}.{ext}'
    saved_path = storage.save(path, file_bytes)

    source = ImageSource.objects.create(
        sha256=sha, original_path=saved_path, content_type=content_type,
        width=width, height=height, bytes_size=len(file_bytes),
        uploaded_by=uploaded_by if (uploaded_by and getattr(uploaded_by, 'is_authenticated', False)) else None,
        status=SourceStatus.PENDING,
    )

    # Outbox: async variant generation picks this up.
    try:
        from apps.outbox.service import publish
        publish(
            topic='image.uploaded',
            payload={'source_id': source.id, 'sha256': sha,
                     'content_type': content_type, 'bytes': len(file_bytes)},
            dedupe_key=f'image.uploaded:{source.id}',
            ref_type='image_source', ref_id=str(source.id),
        )
    except Exception:
        log.debug('image.uploaded publish failed', exc_info=True)

    return source


# ─── Generate variants ─────────────────────────────────────────────────────

def generate_variants_for_source(source: ImageSource, *,
                                  storage=None,
                                  formats: tuple = VARIANT_FORMATS,
                                  sizes: dict = VARIANT_SIZES) -> dict:
    """Generate every (variant × format) combination. Idempotent — already-
    materialised variants are skipped. Updates source.status when done.

    Returns: {'created': N, 'skipped': N, 'errors': N, 'failures': [...]}
    """
    from PIL import Image, UnidentifiedImageError

    storage = storage or _DefaultStorage()

    # Load the original ONCE
    try:
        # default_storage.open is the standard way to read; we wrap it
        # so tests can inject an in-memory storage that returns bytes.
        if hasattr(storage, 'open'):
            f = storage.open(source.original_path)
            data = f.read()
            f.close()
        else:
            with default_storage.open(source.original_path) as f:
                data = f.read()
        original = Image.open(io.BytesIO(data))
        # Force load so format/size are populated before we close the file.
        original.load()
    except (UnidentifiedImageError, FileNotFoundError, OSError) as e:
        ImageSource.objects.filter(pk=source.pk).update(
            status=SourceStatus.FAILED,
            last_error=f'{type(e).__name__}: {e}'[:300],
        )
        return {'created': 0, 'skipped': 0, 'errors': 1,
                'failures': [str(e)]}

    # Pillow's resize keeps the source mode (RGB / RGBA / etc.). Normalise
    # to RGB for JPEG (which can't carry alpha) — keep RGBA for WebP.
    summary = {'created': 0, 'skipped': 0, 'errors': 0, 'failures': []}
    has_alpha = original.mode in ('RGBA', 'LA')

    existing = set(
        ImageVariant.objects.filter(source=source)
        .values_list('variant', 'format')
    )

    for variant_name, (max_w, max_h, crop_square, jpeg_q) in sizes.items():
        for fmt in formats:
            if (variant_name, fmt) in existing:
                summary['skipped'] += 1
                continue
            try:
                im = original.copy()

                if crop_square:
                    # Center-crop to a square before resize — thumbnails
                    # look better that way than letter-boxed.
                    short = min(im.size)
                    left = (im.size[0] - short) // 2
                    top = (im.size[1] - short) // 2
                    im = im.crop((left, top, left + short, top + short))

                # Target dimensions
                if max_h is None:
                    # Width-bound: preserve aspect
                    if im.size[0] > max_w:
                        ratio = max_w / im.size[0]
                        target = (max_w, int(im.size[1] * ratio))
                        im = im.resize(target, Image.LANCZOS)
                else:
                    im.thumbnail((max_w, max_h), Image.LANCZOS)

                buf = io.BytesIO()
                if fmt == 'jpeg':
                    if has_alpha:
                        # JPEG can't carry alpha — flatten on white background
                        bg = Image.new('RGB', im.size, (255, 255, 255))
                        bg.paste(im, mask=im.split()[-1] if im.mode in ('RGBA', 'LA') else None)
                        im = bg
                    elif im.mode != 'RGB':
                        im = im.convert('RGB')
                    im.save(buf, format='JPEG', quality=jpeg_q, optimize=True,
                             progressive=True)
                elif fmt == 'webp':
                    im.save(buf, format='WebP', quality=jpeg_q + 5,
                             method=4)  # higher quality knob for WebP
                else:
                    continue  # unknown format

                data = buf.getvalue()
                ext = fmt
                path = (f'imagery/variants/{source.sha256[:2]}/'
                        f'{source.sha256}_{variant_name}.{ext}')
                saved = storage.save(path, data)
                ImageVariant.objects.create(
                    source=source, variant=variant_name, format=fmt,
                    storage_path=saved, width=im.size[0], height=im.size[1],
                    bytes_size=len(data),
                )
                summary['created'] += 1
            except Exception as e:
                summary['errors'] += 1
                summary['failures'].append(f'{variant_name}/{fmt}: {e}')
                log.warning('variant gen failed for %s/%s/%s: %s',
                             source.pk, variant_name, fmt, e)

    # Update source status
    if summary['errors'] == 0:
        new_status = SourceStatus.READY
    elif summary['created'] > 0:
        new_status = SourceStatus.PARTIAL
    else:
        new_status = SourceStatus.FAILED
    ImageSource.objects.filter(pk=source.pk).update(
        status=new_status,
        last_error='; '.join(summary['failures'])[:300] if summary['failures'] else '',
        updated_at=timezone.now(),
    )
    return summary


# ─── Variant lookup ───────────────────────────────────────────────────────

def get_variant_url(source: ImageSource, variant: str,
                    format: str = 'webp') -> str | None:
    """Constant-time URL lookup. Returns None if missing — caller can
    fall back to source.original_path or kick off generation."""
    storage = _DefaultStorage()
    row = ImageVariant.objects.filter(
        source=source, variant=variant, format=format,
    ).only('storage_path').first()
    if row is None:
        return None
    return storage.url(row.storage_path)


def best_variant_url(source: ImageSource, variant: str,
                     accept_webp: bool = True) -> str | None:
    """Pick the smallest available format for this variant. Returns webp
    if available AND caller accepts it; else jpeg; else None."""
    if accept_webp:
        url = get_variant_url(source, variant, 'webp')
        if url:
            return url
    return get_variant_url(source, variant, 'jpeg')
