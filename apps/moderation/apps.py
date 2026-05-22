from django.apps import AppConfig


class ModerationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.moderation"

    def ready(self):
        """Connect the post_save moderation signals once Django has
        finished loading all apps. Without this, the moderation hook
        is dead code (which is exactly what the audit found —
        ContentFlag.check_content() existed but was never called
        from any code path).
        """
        try:
            from . import signals
            signals.register()
        except Exception:
            # Don't break app startup if signals fail to register
            # (would be an import-time bug; logged elsewhere).
            import logging
            logging.getLogger(__name__).exception(
                'moderation: signal registration failed at startup'
            )
