# apps/admin_backend/apps.py
from django.apps import AppConfig


class AdminBackendConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admin_backend"
    label = "admin_backend"

    def ready(self):
        # super().ready()
        # no super() call as it is not required for this basic config
        from . import events  # noqa: F401

