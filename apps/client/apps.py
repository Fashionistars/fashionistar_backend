# apps/client/apps.py
"""
Client domain AppConfig.

Handles post-startup EventBus listener registration for:
  - user.registered (role=client)  → provision ClientProfile
  - user.verified                  → activate client account
"""
from django.apps import AppConfig


class ClientConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.client"
    verbose_name = "Client Domain"
    label = "client"

    def ready(self) -> None:
        """Wire EventBus listeners — imported lazily to avoid circular imports."""
        from apps.client.events import register_listeners  # noqa: F401
        register_listeners()
