from django.apps import AppConfig


class DataAnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data_analytics'
    label = 'data_analytics'
    verbose_name = 'Data & Analytics Platform'
