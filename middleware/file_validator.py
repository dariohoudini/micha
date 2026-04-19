import logging
from rest_framework.exceptions import ValidationError

logger = logging.getLogger("micha")


def validate_image(file_obj):
    _validate(file_obj, ["image/jpeg", "image/png", "image/webp", "image/gif"], "image")


def validate_video(file_obj):
    _validate(file_obj, ["video/mp4", "video/quicktime", "video/webm"], "video")


def validate_document(file_obj):
    _validate(file_obj, ["application/pdf", "image/jpeg", "image/png"], "document")


def _validate(file_obj, allowed, category):
    if not file_obj:
        return
    try:
        import magic
        file_obj.seek(0)
        mime = magic.from_buffer(file_obj.read(2048), mime=True)
        file_obj.seek(0)
        if mime not in allowed:
            raise ValidationError(
                f"Invalid {category} type. Allowed: {', '.join(t.split('/')[1] for t in allowed)}"
            )
    except ImportError:
        logger.warning("python-magic not installed — file type validation skipped. Run: pip install python-magic")
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(0)
    if size > 5 * 1024 * 1024:
        raise ValidationError("File too large. Maximum 5 MB.")
