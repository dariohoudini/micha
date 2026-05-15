from django.apps import AppConfig


class SagasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sagas'
    verbose_name = 'Sagas (durable, recoverable multi-step workflows)'

    def ready(self):
        # Auto-discover saga definitions in every app's `saga_defs.py` module.
        # Mirrors the outbox handler discovery pattern.
        from django.apps import apps as django_apps
        from importlib import import_module
        for cfg in django_apps.get_app_configs():
            try:
                import_module(f'{cfg.name}.saga_defs')
            except ModuleNotFoundError:
                pass
