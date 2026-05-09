from django.apps import AppConfig


class RiskConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.risk'
    verbose_name = 'Risk (fraud scoring)'

    def ready(self):
        # Import rules so the registry populates on startup
        from . import rules  # noqa: F401
