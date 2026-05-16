from django.apps import AppConfig


class DevKeysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dev_keys'
    verbose_name = 'Developer keys (third-party API access + scopes)'
