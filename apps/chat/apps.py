from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    verbose_name = "Real-Time Messaging"

    def ready(self):
        # Import signal handlers when app is ready
        pass  # noqa: PIE790 — placeholder for future signals
