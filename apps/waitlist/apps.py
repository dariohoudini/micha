from django.apps import AppConfig


class WaitlistConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.waitlist'
    verbose_name = 'Waitlist (back-in-stock subscriptions + conversion tracking)'

    def ready(self):
        # Wire the pre_save / post_save handlers that detect 0→positive
        # stock transitions on Product.
        from . import signals  # noqa: F401
