"""Authentication domain audit helper — Wave B1.

Provides typed, single-responsibility audit recording for all
authentication lifecycle events: login, logout, register, token ops, MFA.
Every call delegates to ``AuditService.log`` — guaranteed never to raise.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID


def _otp_resource_metadata(identifier: object, purpose: str, extra: dict | None = None) -> dict:
    metadata = {"purpose": purpose, **(extra or {})}

    try:
        uuid_value = str(UUID(str(identifier)))
    except (ValueError, TypeError, AttributeError):
        uuid_value = None

    return {
        "resource_type": "UnifiedUser" if uuid_value else None,
        "resource_id": uuid_value,
        "metadata": metadata,
    }


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


def log_password_changed(*, actor, request=None, success: bool = True, reason: str | None = None) -> None:
    """Record a password change event.

    Args:
        actor: The ``UnifiedUser`` who changed their password.
        request: Django HttpRequest.
        success: Whether the change was successful.
        reason: Optional failure reason for audit context.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    action = f"Password changed: {getattr(actor, 'email', str(actor))}"
    if not success:
        action = f"Password change failed for {getattr(actor, 'email', str(actor))}: {reason or 'Unknown'}"

    AuditService.log(
        event_type=EventType.PASSWORD_CHANGED,
        event_category=EventCategory.SECURITY,
        action=action,
        actor=actor,
        request=request,
        severity="info" if success else "warning",
        is_compliance=True,
        metadata={"success": success, "reason": reason} if reason else {"success": success},
    )


def log_password_reset_requested(*, email: str, user_exists: bool, request=None) -> None:
    """Record a password reset request.

    Args:
        email: The email requesting the reset.
        user_exists: Whether a user with this email was found (security signal).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PASSWORD_RESET_REQUEST,
        event_category=EventCategory.AUTHENTICATION,
        action=f"Password reset requested for: {email} (User Exists: {user_exists})",
        actor_email=email,
        request=request,
        metadata={"user_exists": user_exists},
    )


def log_password_reset_completed(*, actor, request=None, metadata: dict | None = None) -> None:
    """Record a successful password reset completion.

    Args:
        actor: The user who successfully reset their password.
        request: Django HttpRequest.
        metadata: Optional additional context (e.g. flow: 'email' vs 'phone').
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PASSWORD_RESET_DONE,
        event_category=EventCategory.SECURITY,
        action=f"Password reset completed successfully: {getattr(actor, 'email', str(actor))}",
        actor=actor,
        request=request,
        severity="info",
        is_compliance=True,
        metadata=metadata,
    )


def log_password_reset_failed(*, request=None, reason: str, actor=None, actor_email: str | None = None, metadata: dict | None = None) -> None:
    """Record a failed password reset attempt.

    Args:
        request: Django HttpRequest.
        reason: Human-readable failure reason.
        actor: The user if identified.
        actor_email: Email if user not found.
        metadata: Optional context.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    # ── Forensic: Precise failure tracking ──────────────────────────────
    # Records exactly why the reset failed (expired token, invalid link, etc.)
    AuditService.log(
        event_type=EventType.PASSWORD_RESET_FAILED,
        event_category=EventCategory.SECURITY,
        action=f"Password reset failed: {reason}",
        actor=actor,
        actor_email=actor_email or getattr(actor, 'email', None),
        request=request,
        severity="warning",
        error_message=reason,
        is_compliance=True,
        metadata=metadata,
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

def log_otp_generated(*, user_id: Any, purpose: str, request: Any = None) -> None:
    """Record the generation of a new OTP.

    Args:
        user_id: The primary key of the user for whom the OTP was generated.
        purpose: The context of the OTP (e.g., 'verify', 'reset', 'login').
        request: Optional Django HttpRequest for context.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    resource_context = _otp_resource_metadata(user_id, purpose)

    AuditService.log(
        event_type=EventType.OTP_GENERATED,
        event_category=EventCategory.AUTHENTICATION,
        action=f"OTP generated for User: {user_id} (Purpose: {purpose})",
        request=request,
        resource_type=resource_context["resource_type"],
        resource_id=resource_context["resource_id"],
        metadata=resource_context["metadata"],
    )


def log_otp_verified(*, user_id: Any, purpose: str, request: Any = None) -> None:
    """Record a successful OTP verification.

    Args:
        user_id: The primary key of the user who verified the OTP.
        purpose: The context of the OTP.
        request: Optional Django HttpRequest for context.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    resource_context = _otp_resource_metadata(user_id, purpose)

    AuditService.log(
        event_type=EventType.OTP_VERIFIED,
        event_category=EventCategory.AUTHENTICATION,
        action=f"OTP verified successfully for User: {user_id} (Purpose: {purpose})",
        request=request,
        resource_type=resource_context["resource_type"],
        resource_id=resource_context["resource_id"],
        metadata=resource_context["metadata"],
    )


def log_otp_failed(*, identifier: str, purpose: str, reason: str, request: Any = None) -> None:
    """Record a failed OTP verification attempt.

    Args:
        identifier: The identifier used (e.g., user_id or search identifier).
        purpose: The context of the OTP.
        reason: Why the verification failed (e.g., 'expired', 'invalid').
        request: Optional Django HttpRequest for context.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    resource_context = _otp_resource_metadata(
        identifier,
        purpose,
        extra={"reason": reason, "identifier": identifier},
    )

    AuditService.log(
        event_type=EventType.OTP_FAILED,
        event_category=EventCategory.SECURITY,
        action=f"OTP verification failed for: {identifier} (Purpose: {purpose}, Reason: {reason})",
        request=request,
        resource_type=resource_context["resource_type"],
        resource_id=resource_context["resource_id"],
        metadata=resource_context["metadata"],
        severity="warning",
    )


def log_account_updated(*, actor, request=None, fields_changed: list[str] | None = None, metadata: dict | None = None) -> None:
    """Record an account or profile update event.

    Args:
        actor: The user whose account was updated.
        request: Optional Django HttpRequest for context.
        fields_changed: List of field names that were modified.
        metadata: Additional context for the update.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    action = f"Account updated for: {getattr(actor, 'email', str(actor))}"
    if fields_changed:
        action += f" (Fields: {', '.join(fields_changed)})"

    AuditService.log(
        event_type=EventType.ACCOUNT_UPDATED,
        event_category=EventCategory.AUTHENTICATION,
        action=action,
        actor=actor,
        request=request,
        metadata={
            "fields_changed": fields_changed,
            **(metadata or {})
        },
    )


def log_biometric_registered(*, actor, device_name: str, request=None) -> None:
    """Record a biometric device registration.

    Args:
        actor: The user registering the device.
        device_name: Name or description of the biometric device.
        request: Optional Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.BIOMETRIC_REGISTERED,
        event_category=EventCategory.SECURITY,
        action=f"Biometric device registered: {device_name} for {getattr(actor, 'email', str(actor))}",
        actor=actor,
        request=request,
        metadata={"device_name": device_name},
        severity="warning",  # Security-sensitive action
        is_compliance=True,
    )


def log_biometric_auth(*, actor, success: bool, request=None, reason: str | None = None) -> None:
    """Record a biometric authentication attempt.

    Args:
        actor: The user attempting authentication.
        success: Whether the authentication succeeded.
        request: Optional Django HttpRequest.
        reason: Optional failure reason.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    event_type = EventType.BIOMETRIC_AUTH_SUCCESS if success else EventType.BIOMETRIC_AUTH_FAILED
    action = f"Biometric authentication {'succeeded' if success else 'failed'} for {getattr(actor, 'email', str(actor))}"
    if not success and reason:
        action += f": {reason}"

    AuditService.log(
        event_type=event_type,
        event_category=EventCategory.SECURITY,
        action=action,
        actor=actor,
        request=request,
        severity="info" if success else "warning",
        metadata={"success": success, "reason": reason} if reason else {"success": success},
    )


def log_account_verified(
    *, actor, request=None, method: str = "otp"
) -> None:
    """Record successful account email/phone verification with auto-login.

    This is distinct from log_login_success in that it marks the FIRST-EVER
    successful identity verification of a newly registered account. Called
    immediately after VerifyOTPView activates the user (is_active=True,
    is_verified=True) and issues JWT tokens.

    Why separate from log_login_success?
    - log_login_success → recurring password-based logins
    - log_account_verified → one-time first-activation event (compliance-critical)

    CBN/NDPR compliance: account activation events must be retained for ≥365 days
    and tagged as compliance events for regulatory audits.

    Args:
        actor: The newly verified UnifiedUser instance.
        request: Django HttpRequest for IP/UA auto-extraction.
        method: Verification method used ('otp', 'email_link').
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ACCOUNT_VERIFIED,
        event_category=EventCategory.AUTHENTICATION,
        action=(
            f"Account verified and auto-logged in via {method}: "
            f"{getattr(actor, 'email', str(actor))}"
        ),
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        request=request,
        is_compliance=True,
        retention_days=365,
        metadata={"verification_method": method},
    )

