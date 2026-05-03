"""
Celery Configuration for MICHA Express
Beat schedule is defined in config/settings.py (CELERY_BEAT_SCHEDULE)
Tasks use idempotency cache locks to prevent double-execution.
"""
import os
from celery import Celery
from celery.schedules import crontab  # noqa - used in settings.py

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("micha")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
