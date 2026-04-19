"""
Image Processing Middleware
Fixes: seller uploads 8MB photo, buyer downloads 8MB for a thumbnail.

On every image upload:
1. Validates MIME type (not just extension)
2. Creates 3 size variants: thumbnail (200px), medium (400px), large (800px)
3. Converts to WebP for 30-40% smaller file size
4. Strips EXIF data (removes GPS location from photos — privacy)

Usage in a view:
    from middleware.image_processor import process_image_upload
    thumbnail_url, medium_url, large_url = process_image_upload(request.FILES['image'])
"""
import io
import logging
from pathlib import Path

logger = logging.getLogger('micha')


def process_image_upload(file_obj, upload_to='products/images/'):
    """
    Process an uploaded image:
    - Validate it's actually an image
    - Strip EXIF (GPS, camera data)
    - Create thumbnail, medium, large variants
    - Convert to WebP
    Returns dict of {size: file_path}
    """
    try:
        from PIL import Image, ExifTags
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        import uuid

        # Read and validate
        file_obj.seek(0)
        img = Image.open(file_obj)
        img.verify()  # Verify it's a valid image

        # Re-open after verify (verify closes the file)
        file_obj.seek(0)
        img = Image.open(file_obj)

        # Convert to RGB (handles PNG with transparency, CMYK etc.)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        # Strip EXIF data (removes GPS location, camera serial number)
        # Privacy: we never want to store where a photo was taken
        data = list(img.getdata())
        img_no_exif = Image.new(img.mode, img.size)
        img_no_exif.putdata(data)
        img = img_no_exif

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

            # Save as WebP for smaller file size
            buffer = io.BytesIO()
            resized.save(buffer, format='WEBP', quality=85, optimize=True)
            buffer.seek(0)

            file_path = f"{upload_to}{size_name}/{base_name}.webp"
            saved_path = default_storage.save(file_path, ContentFile(buffer.read()))
            paths[size_name] = saved_path

        logger.info(f"Image processed: {base_name} — {len(sizes)} variants created")
        return paths

    except ImportError:
        logger.warning("Pillow not installed — image processing skipped")
        return {}
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise ValueError(f"Invalid image file: {str(e)}")


def validate_and_resize_avatar(file_obj):
    """Specific handler for user avatar uploads — square crop + smaller size."""
    try:
        from PIL import Image
        from django.core.files.base import ContentFile
        import io, uuid

        file_obj.seek(0)
        img = Image.open(file_obj)

        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        # Square crop from centre
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))

        # Resize to 300×300
        img = img.resize((300, 300), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=90)
        buffer.seek(0)

        return ContentFile(buffer.read(), name=f"{uuid.uuid4()}.webp")
    except Exception as e:
        raise ValueError(f"Invalid avatar image: {str(e)}")
