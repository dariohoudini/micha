"""apps/imagery/tasks.py — Celery driver for variant generation."""
import logging
from celery import shared_task
from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='imagery.generate_variants', bind=True, max_retries=2,
             soft_time_limit=600, time_limit=720)  # image variants: 10/12 min
def generate_variants_task(self, source_id: int):
    """Generate all variants for one ImageSource. Singleton per-source
    so two workers don't race on the same image."""
    from apps.imagery.models import ImageSource
    from apps.imagery.service import generate_variants_for_source

    @singleton_task(f'imagery.gen:{source_id}')
    def _run():
        src = ImageSource.objects.filter(pk=source_id).first()
        if src is None:
            return {'error': 'source_not_found'}
        return generate_variants_for_source(src)

    return _run()
