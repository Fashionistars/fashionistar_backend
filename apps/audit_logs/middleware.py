# apps/audit_logs/middleware.py
"""
Audit context middleware.

Attaches the current HTTP request to a thread-local store so that
AuditService.log() can automatically capture IP, user-agent, method,
path, and actor without needing the caller to pass the request object.

Usage in settings:
    MIDDLEWARE = [
        ...
        'apps.audit_logs.middleware.AuditContextMiddleware',
        ...
    ]
"""

import threading

_audit_ctx = threading.local()


def get_audit_context() -> dict:
    """
    Return the current request's audit context dict.
    Returns an empty dict outside of a request (e.g. Celery tasks).
    """
    return getattr(_audit_ctx, "ctx", {})


class AuditContextMiddleware:
    """
    Lightweight middleware: stores request context in thread-local storage.

    Populates:
        ip_address      — real IP (handles X-Forwarded-For)
        user_agent      — raw UA string
        request_method  — GET / POST / PUT / PATCH / DELETE
        request_path    — URL path
        actor           — authenticated user (None if anonymous)
        actor_email     — email snapshot
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Populate context before the view runs
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = (xff.split(",")[0].strip() if xff
              else request.META.get("REMOTE_ADDR"))

        user = getattr(request, "user", None)
        actor_email = None
        if user and user.is_authenticated:
            actor_email = getattr(user, "email", None)

        _audit_ctx.ctx = {
            "ip_address":     ip,
            "user_agent":     request.META.get("HTTP_USER_AGENT", ""),
            "request_method": request.method,
            "request_path":   request.path,
            "actor":          user if (user and user.is_authenticated) else None,
            "actor_email":    actor_email,
        }

        try:
            response = self.get_response(request)
        finally:
            # Always clear — prevents request context leaking across threads
            _audit_ctx.ctx = {}

        return response
