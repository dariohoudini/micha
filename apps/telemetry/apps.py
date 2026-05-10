from django.apps import AppConfig


class TelemetryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.telemetry'
    verbose_name = 'Telemetry (metrics + alerts)'

    def ready(self):
        # Import metrics so the registry is populated at import time
        from . import metrics  # noqa: F401
