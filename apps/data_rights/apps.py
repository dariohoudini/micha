from django.apps import AppConfig


class DataRightsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data_rights'
    verbose_name = 'Data rights (GDPR-style export and erasure)'
