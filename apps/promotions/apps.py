from django.apps import AppConfig

class promotionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.promotions'

    def ready(self):
        # Wire User Process Flow §7.6 stock-back signal handlers.
        from . import signals  # noqa: F401
