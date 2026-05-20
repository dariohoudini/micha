"""
Image Processing Middleware
Fixes: seller uploads 8MB photo, buyer downloads 8MB for a thumbnail.

On every image upload:
1. Validates MIME type + dimensions + frame count + aspect ratio via
   middleware.image_security.open_safe (decompression-bomb defence).
2. Strips EXIF data (removes GPS location from photos — privacy).
   Memory-cheap: re-save buffer rather than getdata()/putdata().
3. Creates 3 size variants: thumbnail (200px), medium (400px), large (800px).
4. Converts to WebP for 30-40% smaller file size.

The re-encode through PIL also defeats polyglot files (a file that's
both a valid PNG header AND valid HTML/JS) — only the image bytes
make it to storage.

Usage in a view:
    from middleware.image_processor import process_image_upload
    paths = process_image_upload(request.FILES['image'])
"""
import io
import logging

logger = logging.getLogger('micha')


def process_image_upload(file_obj, upload_to='products/images/'):
    """Process an uploaded product image.

    Returns dict {size: file_path} for thumbnail/medium/large variants
    OR an empty dict if Pillow is missing.

    Raises ValueError (via ImageSecurityError) on any preflight
    rejection — caller should map to HTTP 400.
    """
    try:
        from PIL import Image
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from middleware.image_security import open_safe, strip_exif
        import uuid

        # Single chokepoint — magic / dimensions / pixels / aspect /
        # frames all validated BEFORE any pixel data is decoded.
        img = open_safe(file_obj, allow_animation=True)

        try:
            # Strip EXIF — re-save-buffer approach, NOT getdata()/putdata().
            # For multi-frame images, only the first frame is processed
            # for thumbnails (animated thumbnails would explode CPU at
            # listing scale).
            if getattr(img, 'n_frames', 1) > 1:
                img.seek(0)
            img = strip_exif(img)

            # Convert to RGB for WebP encoding consistency.
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            base_name = str(uuid.uuid4())
            sizes = {
                'thumbnail': (200, 200),
                'medium': (400, 400),
                'large': (800, 800),
            }

            paths = {}
            for size_name, (max_w, max_h) in sizes.items():
                resized = img.copy()
                resized.thumbnail((max_w, max_h), Image.LANCZOS)

                buffer = io.BytesIO()
                resized.save(buffer, format='WEBP', quality=85, optimize=True)
                buffer.seek(0)

                file_path = f"{upload_to}{size_name}/{base_name}.webp"
                saved_path = default_storage.save(file_path, ContentFile(buffer.read()))
                paths[size_name] = saved_path

            logger.info(
                'image_processed',
                extra={
                    'base_name': base_name,
                    'variants': len(sizes),
                    'src_size': img.size,
                },
            )
            return paths
        finally:
            try:
                img.close()
            except Exception:
                pass

    except ImportError:
        logger.warning("Pillow not installed — image processing skipped")
        return {}
    except Exception as e:
        # Preserve ImageSecurityError type discrimination via the
        # ValueError MRO. Caller catches ValueError and returns 400.
        logger.error(f"Image processing failed: {e}")
        raise ValueError(f"Invalid image file: {str(e)}")


def validate_and_resize_avatar(file_obj):
    """Specific handler for user avatar uploads — square crop + 300×300.

    Animations rejected — an animated avatar at scale (1M users × 10
    frames × every list view) is a sustained CPU + bandwidth pin.
    """
    try:
        from PIL import Image
        from django.core.files.base import ContentFile
        from middleware.image_security import open_safe, strip_exif
        import uuid

        # Avatars: no animation. Frame-count cap also defends against
        # 10000-frame APNG that passes size cap but blows up encode time.
        img = open_safe(file_obj, allow_animation=False)

        try:
            img = strip_exif(img)
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            # Square crop from centre.
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            img = img.crop((left, top, left + min_dim, top + min_dim))

            # Resize to 300×300.
            img = img.resize((300, 300), Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format='WEBP', quality=90)
            buffer.seek(0)

            return ContentFile(buffer.read(), name=f"{uuid.uuid4()}.webp")
        finally:
            try:
                img.close()
            except Exception:
                pass

    except Exception as e:
        raise ValueError(f"Invalid avatar image: {str(e)}")
