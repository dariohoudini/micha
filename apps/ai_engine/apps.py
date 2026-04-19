"""
apps/ai_engine/apps.py
"""
from django.apps import AppConfig


class AIEngineConfig(AppConfig):
    name = 'apps.ai_engine'
    verbose_name = 'MICHA AI Engine'

    def ready(self):
        from .signals import register_signals
        register_signals()
