from django.apps import AppConfig


class FeedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.feed'
    verbose_name = 'Personalized feed (homepage tile assembly + ranking)'

    def ready(self):
        # Auto-discover tile producers in each app's `feed_producers.py`
        from django.apps import apps as django_apps
        from importlib import import_module
        for cfg in django_apps.get_app_configs():
            try:
                import_module(f'{cfg.name}.feed_producers')
            except ModuleNotFoundError:
                pass
