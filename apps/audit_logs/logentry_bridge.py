# apps/audit_logs/logentry_bridge.py
"""
Django-AuditLog LogEntry Bridge (Enterprise Enhancement E4)
============================================================
Mirrors every django-auditlog LogEntry save into our AuditEventLog so:
  - One unified search surface for ALL admin changes (django-auditlog ORM
    level + our structured AuditEventLog business events)
  - Admin activity shows up in AuditEventLog with full geo-IP + UA enrichment
  - Superadmin compliance dashboard can query a single table

Architecture
─────────────
django-auditlog saves a LogEntry on every model.save() / model.delete()
when the model is registered with auditlog.register(). We connect to
Django's post_save signal on LogEntry to mirror the data.

This is enabled in audit_logs/apps.py ready() so the signal is only
connected once, after all apps are loaded.

Performance
───────────
• The bridge fires ONLY when AuditContextMiddleware has populated
  _audit_ctx (i.e., inside a real HTTP request or admin session).
• Uses AuditService._dispatch() which writes to Celery async —
  NEVER adds latency to the admin request path.
• Exempts system/automated saves (no request context = no bridge event).

Idempotency
───────────
Since AuditedModelAdmin.save_model() ALSO writes an AuditEventLog row,
the bridge skips the duplicate by checking the action: if the LogEntry
action is CREATE/UPDATE/DELETE from an admin panel path we still write
the bridge entry (different record: one from our mixin, one from auditlog).
Both are USEFUL — our mixin captures old_values/new_values diff WITH
media URL snapshots; the bridge captures the auditlog-native changes dict.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def connect_logentry_bridge() -> None:
    """
    Connect the LogEntry post_save signal.

    Called from AuditLogsConfig.ready() — idempotent, safe to call multiple times.
    """
    try:
        from auditlog.models import LogEntry
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        @receiver(post_save, sender=LogEntry, dispatch_uid="audit_logentry_bridge")
        def _on_logentry_saved(sender, instance: LogEntry, created: bool, **kwargs):
            """Mirror django-auditlog LogEntry → AuditEventLog (async, never blocks)."""
            if not created:
                return  # LogEntries are immutable — only process new ones

            try:
                from apps.audit_logs.middleware import get_audit_context
                ctx = get_audit_context()

                # Only bridge when inside an HTTP request context
                # (avoids noise from management commands / Celery tasks)
                if not ctx:
                    return

                from apps.audit_logs.services.audit import AuditService
                from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

                # Map LogEntry action → severity
                # django-auditlog action codes: 0=create, 1=update, 2=delete, 3=access
                _ACTION_SEVERITY = {
                    0: SeverityLevel.INFO,
                    1: SeverityLevel.INFO,
                    2: SeverityLevel.WARNING,
                    3: SeverityLevel.INFO,
                }
                _ACTION_VERB = {
                    0: "created",
                    1: "updated",
                    2: "deleted",
                    3: "accessed",
                }

                action_code = getattr(instance, "action", 1)
                verb = _ACTION_VERB.get(action_code, "modified")
                severity = _ACTION_SEVERITY.get(action_code, SeverityLevel.INFO)

                # Build actor info from LogEntry
                actor = ctx.get("actor")
                actor_email = ctx.get("actor_email")

                # Prefer LogEntry's actor if ctx is empty
                try:
                    if not actor and instance.actor_id:
                        actor = instance.actor
                        actor_email = getattr(actor, "email", None)
                except Exception:
                    pass

                model_name = (
                    getattr(instance.content_type, "model", "unknown")
                    if hasattr(instance, "content_type") and instance.content_type
                    else "unknown"
                )

                # Build changes summary
                changes = {}
                try:
                    changes = dict(instance.changes or {})
                except Exception:
                    pass

                AuditService.log(
                    event_type=EventType.ADMIN_ACTION,
                    event_category=EventCategory.ADMIN,
                    severity=severity,
                    action=(
                        f"[django-auditlog] Admin {verb} {model_name} "
                        f"(pk={instance.object_id})"
                    ),
                    actor=actor,
                    actor_email=actor_email,
                    ip_address=ctx.get("ip_address"),
                    user_agent=ctx.get("user_agent"),
                    request_method=ctx.get("request_method"),
                    request_path=ctx.get("request_path"),
                    resource_type=model_name,
                    resource_id=str(instance.object_id) if instance.object_id else None,
                    new_values=changes if changes else None,
                    metadata={
                        "source": "django_auditlog_bridge",
                        "logentry_pk": str(instance.pk),
                        "action_code": action_code,
                    },
                    is_compliance=True,
                )

            except Exception:
                # Bridge must NEVER crash the original save
                logger.debug(
                    "logentry_bridge: failed to mirror LogEntry pk=%s",
                    getattr(instance, "pk", "?"),
                    exc_info=False,
                )

    except ImportError:
        # django-auditlog not installed → bridge is a no-op
        logger.debug("logentry_bridge: django-auditlog not installed, bridge disabled")
