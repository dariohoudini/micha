"""
Celery beat: hourly anomaly check.

Wire in your beat schedule:

    CELERY_BEAT_SCHEDULE = {
        ...
        'telemetry-anomaly-check': {
            'task': 'telemetry.run_anomaly_checks',
            'schedule': 3600.0,  # hourly
        },
    }
"""
from celery import shared_task

from .anomaly import run_all


@shared_task(name='telemetry.run_anomaly_checks', ignore_result=True)
def run_anomaly_checks():
    run_all()
    return 'ok'
