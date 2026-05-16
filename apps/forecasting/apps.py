from django.apps import AppConfig


class ForecastingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.forecasting'
    verbose_name = 'Inventory forecasting (demand + reorder recommendations)'
