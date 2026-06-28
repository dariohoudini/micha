from django.apps import AppConfig


class BuyerEngagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.buyer_engagement'
    label = 'buyer_engagement'
    verbose_name = 'Buyer Acquisition & Retention'

    def ready(self):
        from . import signals  # noqa: F401
