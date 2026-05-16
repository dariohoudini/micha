from django.apps import AppConfig


class TwoFactorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.two_factor'
    verbose_name = 'Two-factor authentication (TOTP + backup codes + trusted devices)'
