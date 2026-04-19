"""
File Upload Validator
Validates files by their actual content (MIME sniffing), not their filename extension.
A .php file renamed to .jpg will be detected and rejected.

Requires: pip install python-magic
On Mac:   brew install libmagic
On Linux: apt-get install libmagic1
"""
import magic
import logging
from django.conf import settings
from rest_framework.exceptions import ValidationError

logger = logging.getLogger('micha')


def validate_image(file_obj):
    """
    Validate an uploaded image file.
    Raises ValidationError if the file is not a valid image type.
    Use in serialisers: validate_image(self.validated_data['image'])
    """
    allowed = getattr(settings, 'ALLOWED_IMAGE_TYPES', [
        'image/jpeg', 'image/png', 'image/webp', 'image/gif'
    ])
    _validate_file(file_obj, allowed, 'image')


def validate_video(file_obj):
    allowed = getattr(settings, 'ALLOWED_VIDEO_TYPES', [
        'video/mp4', 'video/quicktime', 'video/webm'
    ])
    _validate_file(file_obj, allowed, 'video')


def validate_document(file_obj):
    """For verification documents — PDF or image only."""
    allowed = getattr(settings, 'ALLOWED_DOC_TYPES', [
        'application/pdf', 'image/jpeg', 'image/png'
    ])
    _validate_file(file_obj, allowed, 'document')


def _validate_file(file_obj, allowed_types, file_category):
    if not file_obj:
        return

    # Read first 2048 bytes for MIME detection (doesn't consume the whole file)
    file_obj.seek(0)
    header = file_obj.read(2048)
    file_obj.seek(0)

    try:
        mime = magic.from_buffer(header, mime=True)
    except Exception as e:
        logger.error(f"MIME detection failed: {e}")
        raise ValidationError(f"Could not verify {file_category} file type.")

    if mime not in allowed_types:
        logger.warning(
            f"Blocked upload: detected MIME {mime} not in allowed types for {file_category}. "
            f"Filename: {getattr(file_obj, 'name', 'unknown')}"
        )
        raise ValidationError(
            f"Invalid {file_category} format. "
            f"Allowed types: {', '.join(t.split('/')[1] for t in allowed_types)}."
        )

    # SECURITY: Check file size
    file_obj.seek(0, 2)  # seek to end
    size = file_obj.tell()
    file_obj.seek(0)

    max_size = 5 * 1024 * 1024  # 5 MB
    if size > max_size:
        raise ValidationError(f"File too large. Maximum size is 5 MB.")
