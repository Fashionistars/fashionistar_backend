# apps/admin_backend/apps.py
from django.apps import AppConfig


class AdminBackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.admin_backend'
    label = 'admin_backend'

    def ready(self):
        super().ready()
        from . import signals  # noqa: F401

        # ── django-auditlog: register all admin_backend models ──────────────
        # LogEntry rows are created by django-auditlog on every save/delete,
        # complementing our AuditedModelAdmin which writes to AuditEventLog.
        try:
            from auditlog.registry import auditlog
            from apps.admin_backend.models import Brand, Category, Collections

            auditlog.register(Brand)
            auditlog.register(Category)
            auditlog.register(Collections)
        except Exception:
            import logging
            logging.getLogger('application').debug(
                "django-auditlog registration skipped (not yet available)"
            )
