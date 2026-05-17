"""
apps/imagery/outbox_handlers.py — picks up 'image.uploaded' events
and queues the variant-generation task.
"""
import logging
from apps.outbox.handlers import handler

log = logging.getLogger(__name__)


@handler('image.uploaded')
def _on_image_uploaded(payload):
    source_id = payload.get('source_id')
    if not source_id:
        return
    try:
        from apps.imagery.tasks import generate_variants_task
        generate_variants_task.delay(source_id)
    except Exception:
        # Celery unavailable (tests) → run inline as a safety net so
        # the smoke can verify behaviour without a worker.
        from apps.imagery.models import ImageSource
        from apps.imagery.service import generate_variants_for_source
        src = ImageSource.objects.filter(pk=source_id).first()
        if src is not None:
            generate_variants_for_source(src)
