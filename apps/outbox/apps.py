from django.apps import AppConfig


class OutboxConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.outbox'
    verbose_name = 'Outbox (transactional event publishing)'

    def ready(self):
        # Auto-discover handlers in every app's `outbox_handlers.py`
        from django.apps import apps as django_apps
        from importlib import import_module
        for cfg in django_apps.get_app_configs():
            try:
                import_module(f'{cfg.name}.outbox_handlers')
            except ModuleNotFoundError:
                pass
