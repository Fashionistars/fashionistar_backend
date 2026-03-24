# apps/audit_logs/middleware.py
"""
Enterprise Audit Context Middleware — Production Grade.

Enhancements vs. v1:
  [E1] Correlation ID: extracts X-Request-ID / X-Correlation-ID header and
       stores it in thread-local so every AuditService.log() call auto-tags
       with the same correlation ID — enabling cross-service distributed tracing.

  [E3] Auto Failed API Capture: on response status >= 400 (and not 401 on
       public paths / OPTIONS / HEAD) fires an async AuditService.log() for
       API_CALL or SYSTEM_ERROR so every failure is captured without the view
       needing to explicitly call AuditService.

Usage in settings:
    MIDDLEWARE = [
        ...
        'apps.audit_logs.middleware.AuditContextMiddleware',
        ...
    ]
"""

from __future__ import annotations

import threading
import uuid
import logging

logger = logging.getLogger(__name__)

_audit_ctx = threading.local()


def get_audit_context() -> dict:
    """
    Return the current request's audit context dict.
    Returns an empty dict outside of a request (e.g. Celery tasks).
    """
    return getattr(_audit_ctx, "ctx", {})


# Paths that should NOT generate automatic 4xx/5xx audit events
# (e.g., health checks, metrics, static files, favicon — too noisy)
_AUTO_CAPTURE_EXEMPT_PREFIXES = (
    "/health",
    "/metrics",
    "/static/",
    "/favicon.ico",
    "/__debug__/",
    "/admin/jsi18n/",
)

# HTTP methods that should NOT generate automatic failed audit events
_AUTO_CAPTURE_EXEMPT_METHODS = frozenset({"OPTIONS", "HEAD"})


class AuditContextMiddleware:
    """
    Enterprise audit middleware with two responsibilities:

    1. Context injection: populates a thread-local store with request metadata
       (IP, UA, method, path, actor, correlation_id) so AuditService.log()
       can auto-enrich without requiring callers to pass the request.

    2. Auto failed API capture: on every response >= 400, fires an async
       AuditService.log() event (API_CALL / SYSTEM_ERROR) so all failures
       are captured without the view needing explicit audit calls.

    Thread Safety
    ─────────────
    Uses threading.local() — safe for multi-threaded WSGI servers (gunicorn,
    uWSGI). Each thread gets its own _audit_ctx.ctx dict, cleared at the end
    of every request in the finally block.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── 1. Build correlation ID (E1) ──────────────────────────────────
        # Prefer header from API gateway / load balancer, generate UUID7 if absent
        correlation_id = (
            request.META.get("HTTP_X_REQUEST_ID")
            or request.META.get("HTTP_X_CORRELATION_ID")
            or str(uuid.uuid4())
        )

        # ── 2. Resolve real IP (X-Forwarded-For safe) ─────────────────────
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = (xff.split(",")[0].strip() if xff
              else request.META.get("REMOTE_ADDR"))

        # ── 3. Resolve actor (may be AnonymousUser at middleware time) ─────
        user = getattr(request, "user", None)
        actor = user if (user and getattr(user, "is_authenticated", False)) else None
        actor_email = getattr(actor, "email", None)

        # ── 4. Populate thread-local context ──────────────────────────────
        _audit_ctx.ctx = {
            "ip_address":      ip,
            "user_agent":      request.META.get("HTTP_USER_AGENT", ""),
            "request_method":  request.method,
            "request_path":    request.path,
            "actor":           actor,
            "actor_email":     actor_email,
            "correlation_id":  correlation_id,
        }

        # ── 5. Inject correlation ID into request for downstream use ───────
        request.correlation_id = correlation_id

        try:
            response = self.get_response(request)
        except Exception:
            _audit_ctx.ctx = {}
            raise

        # ── 6. Auto failed API capture (E3) ───────────────────────────────
        if (
            response.status_code >= 400
            and request.method not in _AUTO_CAPTURE_EXEMPT_METHODS
            and not any(request.path.startswith(p) for p in _AUTO_CAPTURE_EXEMPT_PREFIXES)
        ):
            self._capture_failed_response(request, response, correlation_id, ip, actor)

        # ── 7. Always inject correlation ID into response headers ──────────
        response["X-Correlation-ID"] = correlation_id

        # ── 8. Always clear — prevents context leaking across threads ─────
        _audit_ctx.ctx = {}

        return response

    def _capture_failed_response(
        self, request, response, correlation_id: str, ip: str | None, actor
    ) -> None:
        """
        Fire-and-forget audit event for failed API responses (4xx/5xx).

        Uses apply_async so it never blocks the response path.
        Swallows ALL exceptions to guarantee zero impact on the HTTP response.

        Excluded:
          - 401 on unauthenticated paths (too noisy, expected)
          - 404 for static file requests
          - Any paths in _AUTO_CAPTURE_EXEMPT_PREFIXES
        """
        # Don't audit 401s on non-admin, non-API paths (pure noise for unauthenticated hits)
        if response.status_code == 401 and not request.path.startswith(("/api/", "/admin/")):
            return

        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

            if response.status_code >= 500:
                event_type = EventType.SYSTEM_ERROR
                event_category = EventCategory.SYSTEM
                severity = SeverityLevel.ERROR
            elif response.status_code in (401, 403):
                event_type = EventType.API_CALL
                event_category = EventCategory.SECURITY
                severity = SeverityLevel.WARNING
            else:
                event_type = EventType.API_CALL
                event_category = EventCategory.SYSTEM
                severity = SeverityLevel.WARNING

            AuditService.log(
                event_type=event_type,
                event_category=event_category,
                severity=severity,
                action=(
                    f"API {request.method} {request.path} → {response.status_code}"
                ),
                actor=actor,
                ip_address=ip,
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                request_method=request.method,
                request_path=request.path,
                response_status=response.status_code,
                metadata={
                    "auto_captured": True,
                    "correlation_id": correlation_id,
                },
                is_compliance=response.status_code >= 500,  # 5xx always compliance
            )
        except Exception:
            # Never let audit capture crash the response
            pass
