# admin_backend/apps.py
from django.apps import AppConfig


class AdminBackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_backend'

    def ready(self):
        super().ready()
        import admin_backend.signals  # Import the signals module