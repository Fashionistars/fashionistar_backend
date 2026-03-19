# apps/audit_logs/services/audit.py
"""
AuditService — high-level API for writing structured audit events.

All writes are NON-BLOCKING: events are dispatched directly to the Celery
broker (Redis) via ``apply_async()`` so the HTTP request path is never
delayed and audit events are NEVER lost on transaction rollback.

Falls back to direct synchronous write if Celery is unavailable so
audit events are NEVER silently dropped.

Usage:
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

    AuditService.log(
        event_type=EventType.LOGIN_SUCCESS,
        event_category=EventCategory.AUTHENTICATION,
        action="User logged in successfully",
        request=request,            # optional — auto-populated by middleware
        actor=request.user,         # optional
        resource_type="UnifiedUser",
        resource_id=str(user.pk),
        old_values=None,
        new_values={"last_login": str(now)},
        metadata={"risk_score": 0.1},
        is_compliance=False,
    )
"""

import logging

logger = logging.getLogger(__name__)


class AuditService:
    """
    Stateless service for writing audit events.

    All classmethods — no instantiation needed.
    """

    @classmethod
    def log(
        cls,
        *,
        event_type: str,
        event_category: str,
        action: str,
        severity: str = "info",
        # Actor
        actor=None,
        actor_email: str | None = None,
        # Request context (auto-filled by middleware if None)
        request=None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_type: str | None = None,
        browser_family: str | None = None,
        os_family: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        response_status: int | None = None,
        duration_ms: float | None = None,
        # Resource
        resource_type: str | None = None,
        resource_id: str | None = None,
        # Diff / context
        old_values: dict | None = None,
        new_values: dict | None = None,
        metadata: dict | None = None,
        error_message: str | None = None,
        # Compliance
        is_compliance: bool = False,
        retention_days: int = 2555,
    ) -> None:
        """
        Record a structured audit event.

        All arguments are keyword-only to prevent positional mistakes.
        Guaranteed NEVER to raise — any error is swallowed and logged.
        """
        try:
            from apps.audit_logs.middleware import get_audit_context
            ctx = get_audit_context()

            # ── Resolve actor ─────────────────────────────────────────
            resolved_actor = actor
            if resolved_actor is None and request is not None:
                u = getattr(request, "user", None)
                if u and u.is_authenticated:
                    resolved_actor = u

            if resolved_actor is None:
                resolved_actor = ctx.get("actor")

            resolved_email = actor_email or getattr(resolved_actor, "email", None)
            if not resolved_email and request:
                resolved_email = ctx.get("actor_email")

            # ── Resolve request context ───────────────────────────────
            def _first(*vals):
                for v in vals:
                    if v:
                        return v
                return None

            xff = None
            if request:
                raw_xff = request.META.get("HTTP_X_FORWARDED_FOR")
                xff = raw_xff.split(",")[0].strip() if raw_xff else None

            resolved_ip   = _first(ip_address, xff,
                                   request.META.get("REMOTE_ADDR") if request else None,
                                   ctx.get("ip_address"))
            resolved_ua   = _first(user_agent,
                                   request.META.get("HTTP_USER_AGENT") if request else None,
                                   ctx.get("user_agent"))
            resolved_meth = _first(request_method,
                                   request.method if request else None,
                                   ctx.get("request_method"))
            resolved_path = _first(request_path,
                                   request.path if request else None,
                                   ctx.get("request_path"))

            # ── UA parsing (graceful — ua-parser is optional) ─────────
            resolved_device  = device_type
            resolved_browser = browser_family
            resolved_os      = os_family
            if resolved_ua and (not device_type or not browser_family):
                try:
                    from user_agents import parse as ua_parse
                    ua = ua_parse(resolved_ua)
                    resolved_device  = resolved_device  or (
                        "mobile"  if ua.is_mobile  else
                        "tablet"  if ua.is_tablet  else
                        "bot"     if ua.is_bot     else
                        "desktop"
                    )
                    resolved_browser = resolved_browser or ua.browser.family or None
                    resolved_os      = resolved_os      or ua.os.family      or None
                except Exception:
                    pass

            # ── Build payload ─────────────────────────────────────────
            payload = dict(
                event_type=event_type,
                event_category=event_category,
                severity=severity,
                action=action,
                actor_id=resolved_actor.pk if resolved_actor else None,
                actor_email=resolved_email,
                ip_address=resolved_ip,
                user_agent=resolved_ua,
                device_type=resolved_device,
                browser_family=resolved_browser,
                os_family=resolved_os,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                request_method=resolved_meth,
                request_path=resolved_path,
                response_status=response_status,
                duration_ms=duration_ms,
                old_values=old_values,
                new_values=new_values,
                metadata=metadata,
                error_message=error_message,
                is_compliance=is_compliance,
                retention_days=retention_days,
            )

            # ── Dispatch (async preferred, sync fallback) ─────────────
            cls._dispatch(payload)

        except Exception:
            logger.warning(
                "AuditService.log() swallowed unexpected error for event=%s",
                event_type, exc_info=True,
            )

    @staticmethod
    def _dispatch(payload: dict) -> None:
        """
        Write the audit event asynchronously via Celery, or synchronously
        if the broker is unavailable.

        IMPORTANT: We call ``apply_async()`` DIRECTLY — NOT inside
        ``transaction.on_commit()``. This ensures:
          1. The task is enqueued to Redis immediately, regardless of
             whether the caller's DB transaction commits or rolls back.
          2. Failed-request audit logs (e.g. validation errors inside
             ``transaction.atomic()``) are NEVER silently dropped.
          3. The Celery worker writes to the DB in its own connection,
             so there is no risk of stale reads or lock contention with
             the caller's transaction.
        """
        try:
            from apps.audit_logs.tasks import write_audit_event

            write_audit_event.apply_async(
                kwargs={"payload": payload},
                retry=False,
                ignore_result=True,
            )
        except Exception:
            # Broker down or Celery misconfigured — write synchronously
            # so events are never dropped.
            _write_sync(payload)


def _write_sync(payload: dict) -> None:
    """Synchronous fallback: write directly to DB."""
    try:
        from apps.audit_logs.models import AuditEventLog
        actor_id = payload.pop("actor_id", None)
        obj = AuditEventLog(**payload)
        if actor_id:
            obj.actor_id = actor_id
        obj.save()
    except Exception:
        logger.exception("AuditService._write_sync() failed for payload=%s", payload)
