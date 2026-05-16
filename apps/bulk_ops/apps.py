from django.apps import AppConfig


class BulkOpsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bulk_ops'
    verbose_name = 'Bulk admin operations (long-running, observable, cancellable)'

    def ready(self):
        # Auto-discover handler modules in every app, mirroring the saga pattern.
        from django.apps import apps as django_apps
        from importlib import import_module
        for cfg in django_apps.get_app_configs():
            try:
                import_module(f'{cfg.name}.bulk_handlers')
            except ModuleNotFoundError:
                pass
