"""
apps/ai/apps.py — AppConfig for the FASHIONISTAR AI engine.
"""
from django.apps import AppConfig


class AIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "AI Orchestration Engine"

    def ready(self):
        """
        Register Django signals for real-time AI data ingestion.
        Signals are imported here to prevent circular import issues.
        """
        try:
            import apps.ai.signals.db_change_signals  # noqa: F401
        except Exception:
            pass
