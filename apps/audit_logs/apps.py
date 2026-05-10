# apps/audit_logs/apps.py
"""
AuditLogs AppConfig — registers signal bridges in ready().
"""
from django.apps import AppConfig


class AuditLogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit_logs"
    verbose_name = "Audit Logs"

    def ready(self):
        """
        Wire up all signal receivers and bridges once Django is ready.

        Registered here:
          E4 — django-auditlog LogEntry bridge (mirrors LogEntry → AuditEventLog)
        """
        try:
            from apps.audit_logs.logentry_bridge import connect_logentry_bridge
            connect_logentry_bridge()
        except Exception:
            import logging
            logging.getLogger("application").debug(
                "AuditLogsConfig.ready: logentry_bridge wiring skipped"
            )
