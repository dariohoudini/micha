from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        # Wire the migration safety guard. We patch the migrate command
        # rather than using pre_migrate signal because pre_migrate fires
        # per-app and doesn't have the full plan — we need plan-level
        # visibility to refuse-or-allow as a single decision.
        from . import migration_hook  # noqa: F401
