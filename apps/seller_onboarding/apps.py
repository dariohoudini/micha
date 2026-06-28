from django.apps import AppConfig


class SellerOnboardingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.seller_onboarding'
    label = 'seller_onboarding'
    verbose_name = 'Seller Acquisition & Onboarding'

    def ready(self):
        # Wire the signal handlers that drive the application state
        # machine. Importing the module is enough — signal connections
        # run at import time.
        from . import signals  # noqa: F401
