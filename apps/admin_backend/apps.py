# apps/admin_backend/apps.py
from django.apps import AppConfig


class AdminBackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.admin_backend'
    label = 'admin_backend'

    def ready(self):
        super().ready()
        from . import signals  # noqa: F401
