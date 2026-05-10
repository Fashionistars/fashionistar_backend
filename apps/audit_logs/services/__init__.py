"""
apps/audit_logs/services/__init__.py
=====================================
Master barrel for the audit services package.

Domain audit helpers are exposed as lazily-imported submodules to prevent
circular import chains during django.setup(). Import the specific module
you need directly:

    from apps.audit_logs.services import AuditService
    AuditService.log(event_type=..., event_category=..., action=...)

    # OR via domain-specific helpers:
    from apps.audit_logs.services import auth_audit
    auth_audit.log_login_success(actor=user, request=request)

    # OR import the specific function:
    from apps.audit_logs.services.authentication.auth_audit import log_login_success

Design:
    ``AuditService`` is exposed via Python's ``__getattr__`` hook so it is only
    imported on first access (not at module-load time). This preserves the
    zero-circular-import guarantee: Django startup never touches this attribute
    unless a caller explicitly asks for it.
"""

from __future__ import annotations

__all__ = ["AuditService"]


def __getattr__(name: str):
    """Lazy-import gateway — keeps django.setup() safe from circular imports."""
    if name == "AuditService":
        from apps.audit_logs.services.audit import AuditService  # noqa: PLC0415
        return AuditService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
