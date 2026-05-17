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

# Propagate request_id from the dispatching web request to the task's
# log records. Importing the module registers signal handlers
# (@before_task_publish / @task_prerun / @task_postrun).
from middleware import celery_request_id  # noqa: E402, F401
celery_request_id.install_celery_request_id_propagation()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
