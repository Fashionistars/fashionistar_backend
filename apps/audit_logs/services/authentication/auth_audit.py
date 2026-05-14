"""Authentication domain audit helper — Wave B1.

Provides typed, single-responsibility audit recording for all
authentication lifecycle events: login, logout, register, token ops, MFA.
Every call delegates to ``AuditService.log`` — guaranteed never to raise.
"""
from __future__ import annotations


def log_login_success(*, actor, request=None, session_id: str | None = None) -> None:
    """Record a successful login event.

    Args:
        actor: The authenticated ``UnifiedUser`` instance.
        request: Django HttpRequest for IP/UA auto-extraction.
        session_id: JWT jti for session correlation.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.LOGIN_SUCCESS,
        event_category=EventCategory.AUTHENTICATION,
        action=f"User logged in: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        session_id=session_id,
        request=request,
        is_compliance=False,
    )


def log_login_failed(*, email: str, request=None, reason: str = "") -> None:
    """Record a failed login attempt.

    Args:
        email: The email address that was attempted.
        request: Django HttpRequest for IP/UA extraction.
        reason: Human-readable failure reason.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.LOGIN_FAILED,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Login failed for {email}: {reason or 'invalid credentials'}",
        actor_email=email,
        severity="warning",
        request=request,
    )


def log_login_blocked(
    *,
    email: str,
    actor=None,
    request=None,
    reason: str = "",
    resource_id: str | None = None,
) -> None:
    """Record a blocked login attempt such as inactive, deleted, or unverified."""
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.LOGIN_BLOCKED,
        event_category=EventCategory.SECURITY,
        action=f"Login blocked for {email}: {reason or 'blocked'}",
        actor=actor,
        actor_email=getattr(actor, "email", None) or email,
        resource_type="UnifiedUser" if resource_id else None,
        resource_id=resource_id,
        severity="warning",
        request=request,
        metadata={"reason": reason} if reason else None,
        is_compliance=True,
    )


def log_logout(*, actor, request=None, session_id: str | None = None) -> None:
    """Record a user logout event.

    Args:
        actor: The ``UnifiedUser`` who logged out.
        request: Django HttpRequest.
        session_id: JWT jti being revoked.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.LOGOUT,
        event_category=EventCategory.AUTHENTICATION,
        action=f"User logged out: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        session_id=session_id,
        request=request,
    )


def log_register_success(*, actor, request=None) -> None:
    """Record a successful user registration.

    Args:
        actor: The newly created ``UnifiedUser`` instance.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.REGISTER_SUCCESS,
        event_category=EventCategory.AUTHENTICATION,
        action=f"New user registered: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        request=request,
        is_compliance=True,
        retention_days=365,
    )


def log_register_failed(*, email: str, request=None, reason: str = "") -> None:
    """Record a failed registration attempt.

    Args:
        email: The email address that was attempted.
        request: Django HttpRequest.
        reason: Validation or server failure reason.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.REGISTER_FAILED,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Registration failed for {email}: {reason}",
        actor_email=email,
        severity="warning",
        request=request,
    )


def log_password_changed(*, actor, request=None) -> None:
    """Record a password change event.

    Args:
        actor: The ``UnifiedUser`` who changed their password.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PASSWORD_CHANGED,
        event_category=EventCategory.SECURITY,
        action=f"Password changed: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        request=request,
        severity="warning",
        is_compliance=True,
    )


def log_password_reset_requested(*, email: str, request=None) -> None:
    """Record a password reset request.

    Args:
        email: The email requesting the reset.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PASSWORD_RESET_REQUEST,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Password reset requested for: {email}",
        actor_email=email,
        request=request,
    )


def log_token_refreshed(*, actor, request=None, session_id: str | None = None) -> None:
    """Record a JWT access-token refresh.

    Args:
        actor: The user refreshing their token.
        request: Django HttpRequest.
        session_id: The JWT jti of the refresh token.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.TOKEN_REFRESHED,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Token refreshed: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        session_id=session_id,
        request=request,
    )


def log_mfa_enabled(*, actor, request=None) -> None:
    """Record MFA being enabled on an account.

    Args:
        actor: The user enabling MFA.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MFA_ENABLED,
        event_category=EventCategory.SECURITY,
        action=f"MFA enabled: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        request=request,
        severity="warning",
        is_compliance=True,
    )


def log_suspicious_activity(
    *, actor=None, email: str = "", reason: str, request=None
) -> None:
    """Record a suspicious activity detection event.

    Args:
        actor: The ``UnifiedUser`` if identified; None for anonymous.
        email: Email string if actor is None.
        reason: Description of the suspicious behaviour.
        request: Django HttpRequest for IP/UA.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.SUSPICIOUS_ACTIVITY,
        event_category=EventCategory.SECURITY,
        action=f"Suspicious activity: {reason}",
        actor=actor,
        actor_email=email or None,
        request=request,
        severity="critical",
        is_compliance=True,
        retention_days=2555,  # 7 years
    )
