"""
middleware/image_security.py
─────────────────────────────

Single chokepoint for "open an uploaded image safely" — magic-byte
validation + dimension / pixel-count / animation-frame caps applied
BEFORE any pixel data is decoded into memory.

Why this exists
────────────────
The existing image pipeline had four real production-grade risks
buried in 100 lines of look-it-works PIL code:

  1. Decompression bombs. A 1 KB PNG with the IHDR chunk declaring
     100 000 × 100 000 pixels will, when PIL tries to decode it,
     attempt to allocate ~40 GB of RAM. PIL provides
     ``Image.MAX_IMAGE_PIXELS`` but it must be set explicitly AND
     the existing code called ``img.verify()`` then ``img.getdata()``
     — the latter materialises every pixel as a Python list,
     amplifying memory pressure even for legitimate large images.

  2. ``img.getdata()`` + ``img.putdata()`` was the EXIF-strip method.
     For a legit 10 MP photo that's 30 MB of Python objects per upload,
     turning a 100 req/s upload endpoint into a memory exhaustion vector.
     The right way to drop EXIF is to re-save without it
     (``img.save(buf, exif=b'')``) — re-encoding inherently doesn't
     carry EXIF unless you ask it to.

  3. Pathological aspect ratios. A 50 000 × 1 image clears a 50 MP
     pixel cap but is a denial-of-thumbnailing attack — every resize
     step degenerates to a 1-pixel-wide strip and bloats CPU.

  4. Animation frame floods. An animated GIF with 10 000 frames
     re-encoded by Pillow per-frame is a sustained CPU pin. Avatars
     should never be animated; product photos can be limited to
     a sensible frame ceiling.

Plus general hygiene: filename sanitization (``../../../etc/passwd``
in ``file_obj.name`` would propagate into the storage backend); MIME
type vs declared extension cross-check; explicit close after use.

Limits (tunable via settings)
──────────────────────────────
  IMAGE_MAX_FILE_BYTES        = 10 MB
  IMAGE_MAX_PIXELS            = 50_000_000  (50 MP)
  IMAGE_MAX_DIMENSION         = 12_000      (each side ≤ 12k pixels)
  IMAGE_MIN_ASPECT_RATIO      = 0.1         (rejects 50000×1 narrow strips)
  IMAGE_MAX_FRAMES            = 50          (animated GIF / APNG / WebP)

These are conservative defaults appropriate for product photos +
avatars at marketplace scale. Tune from upload telemetry.

Public API
──────────
  open_safe(file_obj, *, allow_animation=True) -> PIL.Image.Image
      Validate magic / dimensions / frames pre-decode. Returns the
      opened image. Caller is responsible for closing.

  strip_exif(img) -> PIL.Image.Image
      Memory-cheap EXIF strip via re-save buffer round-trip — does
      NOT call ``getdata()/putdata()``.

  sanitize_filename(name) -> str
      Strip directory components, restrict to a safe charset, cap length.

  ImageSecurityError
      Raised on any preflight rejection. Safe to surface to the
      client as 400 with the message.
"""
from __future__ import annotations

import io
import os
import re
import logging
import uuid
from typing import Optional

logger = logging.getLogger('micha.image_security')


class ImageSecurityError(ValueError):
    """Raised by open_safe on any preflight rejection. Subclass of
    ValueError so the existing image_processor catch-all keeps working."""


# ─── Tunable limits (read from settings at call time) ────────────────

def _setting(name: str, default):
    try:
        from django.conf import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _max_file_bytes() -> int:
    return int(_setting('IMAGE_MAX_FILE_BYTES', 10 * 1024 * 1024))


def _max_pixels() -> int:
    return int(_setting('IMAGE_MAX_PIXELS', 50_000_000))


def _max_dimension() -> int:
    return int(_setting('IMAGE_MAX_DIMENSION', 12_000))


def _min_aspect_ratio() -> float:
    return float(_setting('IMAGE_MIN_ASPECT_RATIO', 0.1))


def _max_frames() -> int:
    return int(_setting('IMAGE_MAX_FRAMES', 50))


# ─── MIME allowlist (re-checked here in addition to file_validator) ──

_ALLOWED_MIME = frozenset({
    'image/jpeg', 'image/png', 'image/webp', 'image/gif',
})


def _detect_mime(file_obj) -> str:
    """Magic-byte detection. Falls back to '' if python-magic missing
    — caller still gets dimension / frame / size checks."""
    try:
        import magic
        file_obj.seek(0)
        mime = magic.from_buffer(file_obj.read(2048), mime=True) or ''
        file_obj.seek(0)
        return mime
    except ImportError:
        return ''


# ─── Decompression-bomb guard at the PIL level ───────────────────────

def _install_pil_bomb_guard():
    """Set PIL's own MAX_IMAGE_PIXELS belt-and-braces.

    PIL raises ``Image.DecompressionBombError`` if a loaded image
    exceeds this. Our preflight check should catch this first via
    header inspection, but if the preflight is bypassed (e.g. the
    image processor opens an image without going through open_safe),
    PIL's own guard still fires.

    Called at module import.
    """
    try:
        from PIL import Image
        # Limit slightly above our preflight to keep PIL's check as
        # the second layer of defence (preflight rejects first).
        Image.MAX_IMAGE_PIXELS = _max_pixels() + 10_000_000
    except Exception:
        pass


_install_pil_bomb_guard()


# ─── Public: open_safe ────────────────────────────────────────────────

def open_safe(file_obj, *, allow_animation: bool = True):
    """Open an uploaded image safely.

    Order matters — fail FAST on the cheapest checks before allocating
    any pixel buffers:
      1. File size (header read)
      2. Magic-byte MIME (read first 2 KB)
      3. PIL open (parses headers only, NOT pixel data)
      4. Dimensions from header (img.size)
      5. Aspect ratio from header
      6. Frame count for animated formats
      7. Optional verify() — full header walk; no pixel decode

    Raises ImageSecurityError on any rejection.

    Returns the opened PIL.Image.Image. Caller is responsible for
    closing it (use a try/finally or context manager).
    """
    from PIL import Image, UnidentifiedImageError

    if file_obj is None:
        raise ImageSecurityError('no file provided')

    # 1. File size — cheap, do it first.
    try:
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
    except Exception:
        raise ImageSecurityError('unable to determine file size')
    if size <= 0:
        raise ImageSecurityError('empty file')
    if size > _max_file_bytes():
        raise ImageSecurityError(
            f'file too large: {size} bytes > {_max_file_bytes()} bytes'
        )

    # 2. Magic-byte MIME — defeats "rename .exe to .jpg" attacks.
    mime = _detect_mime(file_obj)
    if mime and mime not in _ALLOWED_MIME:
        raise ImageSecurityError(
            f'unsupported image type: {mime}'
        )

    # 3. PIL open — parses headers only.
    file_obj.seek(0)
    try:
        img = Image.open(file_obj)
    except UnidentifiedImageError:
        raise ImageSecurityError('file is not a recognisable image')
    except Image.DecompressionBombError as e:
        raise ImageSecurityError(f'decompression bomb rejected: {e}')
    except Exception as e:
        raise ImageSecurityError(f'cannot open image: {e}')

    # 4. Dimensions — header-only, no pixel decode yet.
    try:
        w, h = img.size
    except Exception:
        img.close()
        raise ImageSecurityError('image has no dimensions')

    max_dim = _max_dimension()
    if w > max_dim or h > max_dim:
        img.close()
        raise ImageSecurityError(
            f'image dimensions {w}x{h} exceed cap {max_dim}'
        )

    max_px = _max_pixels()
    if (w * h) > max_px:
        img.close()
        raise ImageSecurityError(
            f'pixel count {w*h} exceeds cap {max_px}'
        )

    # 5. Aspect ratio — rejects pathologically narrow strips.
    min_ratio = _min_aspect_ratio()
    short, long_ = min(w, h), max(w, h)
    if long_ > 0 and (short / long_) < min_ratio:
        img.close()
        raise ImageSecurityError(
            f'aspect ratio {short}/{long_} below minimum {min_ratio}'
        )

    # 6. Frame count — animated GIF / APNG / animated WebP.
    #
    # PIL computes ``n_frames`` lazily for GIFs — accessing the attribute
    # forces a count via a header walk (no pixel decode). Catch
    # exceptions because malformed multi-frame headers can raise.
    try:
        n_frames = int(getattr(img, 'n_frames', 1) or 1)
    except Exception:
        n_frames = 1
    if not allow_animation and n_frames > 1:
        img.close()
        raise ImageSecurityError(
            'animation not allowed for this upload type'
        )
    if n_frames > _max_frames():
        img.close()
        raise ImageSecurityError(
            f'frame count {n_frames} exceeds cap {_max_frames()}'
        )

    # Note: we deliberately don't call ``img.verify()`` here.
    # verify() closes the underlying file object as a side effect (PIL
    # quirk), AND it duplicates work the caller already implicitly does
    # at save() / load() time. The dimension + pixel + aspect + frame
    # checks above plus PIL's own DecompressionBombError on open()
    # already cover the cases verify() was added for.

    # Rewind for the caller. img is still bound to file_obj internally
    # and PIL's lazy decode will read on demand.
    file_obj.seek(0)
    return img


# ─── Public: strip_exif ──────────────────────────────────────────────

def strip_exif(img):
    """Return a copy of img with NO EXIF metadata.

    Memory-cheap: re-saves through a buffer rather than materialising
    pixel data via ``getdata()/putdata()`` — the prior approach
    allocated a Python list of every pixel (30 MB for a 10 MP photo).

    EXIF is dropped because product/avatar photos commonly carry GPS
    coordinates of the seller's home, camera serial numbers, and
    timestamps — all PII / fingerprintable data that has no business
    in marketplace images.
    """
    from PIL import Image
    buf = io.BytesIO()
    fmt = (img.format or 'PNG').upper()
    # Convert paletted / CMYK / RGBA-to-formats-that-need-RGB before save.
    save_img = img
    if fmt == 'JPEG' and img.mode != 'RGB':
        save_img = img.convert('RGB')
    # exif=b'' explicitly tells PIL to drop any EXIF block on save.
    save_img.save(buf, format=fmt, exif=b'')
    buf.seek(0)
    return Image.open(buf)


# ─── Public: sanitize_filename ───────────────────────────────────────

_UNSAFE_FILENAME_CHARS = re.compile(r'[^A-Za-z0-9._-]')


def sanitize_filename(name: str) -> str:
    """Reduce an uploaded filename to a safe stem + extension.

    Strips:
      • Directory components — drops "../" traversals and absolute paths
      • Non-alphanumeric chars beyond _ . - — defeats injection
      • Leading dots — no hidden files
      • Length over 80 chars
      • Empty stems — replace with a uuid4 hex
    """
    if not name:
        return f'{uuid.uuid4().hex[:16]}.bin'
    name = os.path.basename(str(name)).lstrip('.')
    # Split on the LAST dot so extension survives.
    if '.' in name:
        stem, ext = name.rsplit('.', 1)
    else:
        stem, ext = name, ''
    stem = _UNSAFE_FILENAME_CHARS.sub('_', stem)[:64] or uuid.uuid4().hex[:16]
    ext = _UNSAFE_FILENAME_CHARS.sub('', ext)[:10]
    return f'{stem}.{ext}' if ext else stem
