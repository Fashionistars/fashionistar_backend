# apps/audit_logs/apps.py
from django.apps import AppConfig


class AuditLogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit_logs"
    verbose_name = "Audit Logs"

    def ready(self):
        pass  # Reserved for signal registrations if needed
