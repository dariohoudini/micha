from django.apps import AppConfig


class ContentSafetyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.content_safety'
    verbose_name = 'Content safety (scan + escalate + audit, reusable)'
