# apps/authentication/exceptions.py
"""
Advanced Exception Handling Framework for the Authentication Domain.

This module provides:

1. **Typed Exception Classes** — fine-grained exceptions carry their own
   HTTP status code and machine-readable ``default_code``, so views,
   serializers, and global exception handlers can all act on them without
   string parsing.

2. **Legacy Compatibility Aliases** — the original ``AuthenticationException``
   and its sub-classes (``InvalidCredentialsException``, ``OTPExpiredException``,
   ``RateLimitExceededException``, etc.) are preserved so that any existing
   import throughout the codebase continues to work without modification.

3. **Shared Helper Utilities** — ``_get_client_ip`` and ``_log_error`` are
   re-exported here for modules that import them from this file.

Exception Hierarchy
-------------------
AuthenticationError (400)                 ← New enterprise base
  ├─ DuplicateUserError (409)             ← Active duplicate on registration
  ├─ SoftDeletedUserExistsError (409)     ← Soft-deleted duplicate on registration
  ├─ SoftDeletedUserError (403)           ← Login: account is deactivated
  ├─ AccountInactiveError (403)           ← Login: is_active=False (unverified)
  ├─ InvalidCredentialsError (401)        ← Login: wrong password / unknown user
  ├─ AccountDeactivatedError (403)        ← Admin-disabled, not soft-delete
  └─ AccountSuspendedError (403)          ← Suspension workflow

AuthenticationException (401)             ← Legacy base (compatibility)
  ├─ InvalidCredentialsException (401)    ← Legacy alias
  ├─ AccountNotVerifiedException (403)    ← Legacy: unverified account on login
  ├─ OTPExpiredException (401)            ← OTP flow: expired token
  └─ InvalidOTPException (401)            ← OTP flow: wrong token

RateLimitExceededException (429)          ← Standalone rate-limit

Usage
-----
    # New-style (preferred)
    from apps.authentication.exceptions import SoftDeletedUserError
    raise SoftDeletedUserError()

    # Legacy-style (still works)
    from apps.authentication.exceptions import InvalidCredentialsException
    raise InvalidCredentialsException()
"""

import logging
import traceback

from django.conf import settings
from django.core.exceptions import (
    PermissionDenied,
    ValidationError as DjangoValidationError,
)
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied as DRFPermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# Separate logger for the auth domain (maps to 'authentication' log file)
logger = logging.getLogger('application')


# =============================================================================
# NEW ENTERPRISE TYPED EXCEPTIONS
# =============================================================================

class AuthenticationError(APIException):
    """
    Base class for all Fashionistar authentication exceptions.

    HTTP 400 by default; sub-classes override ``status_code`` as needed.
    All sub-classes carry a machine-readable ``default_code`` so the
    global exception handler can distinguish them without isinstance checks.
    """
    status_code    = status.HTTP_400_BAD_REQUEST
    default_detail = "Authentication error."
    default_code   = "authentication_error"


# ---------------------------------------------------------------------------
# Registration errors
# ---------------------------------------------------------------------------

class DuplicateUserError(AuthenticationError):
    """
    Raised when a registration attempt is made with an email or phone
    that already belongs to an *active* (non-deleted) user account.

    HTTP 409 Conflict — the resource already exists.
    """
    status_code    = status.HTTP_409_CONFLICT
    default_detail = (
        "An account with this email or phone already exists. "
        "Please log in or use a different identifier."
    )
    default_code   = "duplicate_user"


class SoftDeletedUserExistsError(AuthenticationError):
    """
    Raised when a registration attempt is made with an email or phone
    that belongs to a *soft-deleted* (deactivated) user account.

    HTTP 409 Conflict — the resource exists but is deactivated.

    The message intentionally does NOT reveal whether the account is
    permanently deleted or just deactivated, to prevent user enumeration.
    Contact-support language guides the user to the right resolution path.
    """
    status_code    = status.HTTP_409_CONFLICT
    default_detail = (
        "An account associated with this email or phone was previously "
        "deactivated on our platform. Please contact our support team "
        "to restore access or use a different identifier."
    )
    default_code   = "deactivated_user_exists"


# ---------------------------------------------------------------------------
# Login errors
# ---------------------------------------------------------------------------

class SoftDeletedUserError(AuthenticationError):
    """
    Raised during *login* when the authenticated user's account has been
    soft-deleted (is_deleted=True).

    HTTP 403 Forbidden — the user is known but access is revoked.

    The response message is intentionally explicit here (post-authentication
    context) so the user understands why they cannot log in and what to do.
    Includes a support URL derived from FRONTEND_URL so frontend can link
    directly to the support page.
    """
    status_code  = status.HTTP_403_FORBIDDEN
    default_code = "account_deactivated"

    def __init__(self, support_url: str = ''):
        from django.conf import settings as _s
        _base        = getattr(_s, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        _support_url = support_url or f"{_base}/support"
        detail = (
            "Your account has been permanently deactivated. "
            f"Please contact our support team to restore access: {_support_url}"
        )
        super().__init__(detail=detail)


class AccountNotVerifiedError(AuthenticationError):
    """
    Raised FIRST during login when the account exists, password is correct,
    but ``is_verified=False`` — meaning the user has not yet completed OTP
    verification after registration.

    HTTP 403 Forbidden.

    The detail message includes actionable URLs so the frontend can
    automatically display a "Verify / Resend OTP" prompt.
    """
    status_code  = status.HTTP_403_FORBIDDEN
    default_code = "account_not_verified"

    def __init__(self, verify_url: str = '', resend_url: str = ''):
        from django.conf import settings as _s
        _base       = getattr(_s, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        _verify_url = verify_url  or f"{_base}/auth/verify-otp"
        _resend_url = resend_url  or f"{_base}/auth/verify-otp"
        detail = (
            "Your account has not been verified yet. "
            "Please check your email or phone for the OTP code we sent during registration. "
            f"Verify your account here: {_verify_url} "
            f"— or request a new code here: {_resend_url}"
        )
        super().__init__(detail=detail)


class AccountInactiveError(AuthenticationError):
    """
    Raised when a user's account is found, password is correct, but
    ``is_active=False`` AND ``is_verified=True`` — indicating an admin
    has explicitly deactivated the account (not a verification issue).

    HTTP 403 Forbidden.
    """
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = (
        "Your account is currently inactive. "
        "Please verify your email/phone or contact support."
    )
    default_code   = "account_inactive"


class InvalidCredentialsError(AuthenticationError):
    """
    Raised when login fails due to incorrect password or unknown identifier.

    HTTP 401 Unauthorized.

    NOTE: The message is kept intentionally vague (does not distinguish
    'wrong password' vs 'unknown user') to prevent user enumeration attacks.
    """
    status_code    = status.HTTP_401_UNAUTHORIZED
    default_detail = (
        "Invalid credentials. "
        "Please check your email/phone and password and try again."
    )
    default_code   = "invalid_credentials"


class AccountDeactivatedError(AuthenticationError):
    """
    Raised when ``is_active=False`` AND ``is_deleted=False`` — meaning an
    admin has explicitly deactivated the account via the Django admin panel
    (not via the soft-delete workflow).

    HTTP 403 Forbidden.

    Includes a support URL derived from FRONTEND_URL so frontend can
    provide a clickable "Contact Support" link.
    """
    status_code  = status.HTTP_403_FORBIDDEN
    default_code = "account_deactivated"

    def __init__(self, support_url: str = ''):
        from django.conf import settings as _s
        _base        = getattr(_s, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        _support_url = support_url or f"{_base}/support"
        detail = (
            "Your account has been deactivated by an administrator. "
            f"Please contact our support team for assistance: {_support_url}"
        )
        super().__init__(detail=detail)


class AccountSuspendedError(AuthenticationError):
    """
    Raised when an account is suspended (is_active=False due to suspension).

    HTTP 403 Forbidden.
    """
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = (
        "Your account has been suspended. "
        "Please contact support for more information."
    )
    default_code   = "account_suspended"


# =============================================================================
# LEGACY EXCEPTION CLASSES  (backward-compatibility aliases)
# =============================================================================

class AuthenticationException(APIException):
    """
    **Legacy base** — preserved so that existing imports continue to work.

    New code should raise ``AuthenticationError`` (or a typed sub-class) instead.
    HTTP 401 Unauthorized.
    """
    status_code    = status.HTTP_401_UNAUTHORIZED
    default_detail = "Authentication failed."
    default_code   = "authentication_failed"


class InvalidCredentialsException(AuthenticationException):
    """
    **Legacy alias** for ``InvalidCredentialsError``.
    HTTP 401 Unauthorized.
    """
    default_detail = "Invalid email/phone or password."
    default_code   = "invalid_credentials"


class AccountNotVerifiedException(AuthenticationException):
    """
    **Legacy** — raised when user attempts to login but account is not verified.
    HTTP 403 Forbidden.
    """
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = "Account not verified. Please verify your email/phone."
    default_code   = "account_not_verified"


class OTPExpiredException(AuthenticationException):
    """
    Raised when user provides an expired OTP.
    HTTP 401 Unauthorized.
    """
    default_detail = "OTP has expired. Please request a new one."
    default_code   = "otp_expired"


class InvalidOTPException(AuthenticationException):
    """
    Raised when OTP doesn't match.
    HTTP 401 Unauthorized.
    """
    default_detail = "Incorrect OTP. Please try again."
    default_code   = "invalid_otp"


class RateLimitExceededException(APIException):
    """
    Custom Rate Limit Exception (replaces default ``Throttled`` where needed).
    HTTP 429 Too Many Requests.
    """
    status_code    = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Too many requests. Please try again later."
    default_code   = "rate_limit_exceeded"


# =============================================================================
# HELPER UTILITIES  (importable from this module for backwards-compat)
# =============================================================================

def _get_client_ip(request) -> str:
    """
    Extract the client's real IP address from a Django request object,
    accounting for reverse proxies (nginx, CloudFlare, AWS ELB).

    Priority order:
        1. ``HTTP_X_FORWARDED_FOR`` header (first IP in chain)
        2. ``HTTP_X_REAL_IP`` header
        3. ``REMOTE_ADDR`` (direct connection)
    """
    try:
        if request is None:
            return 'UNKNOWN'

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()

        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip

        remote_addr = request.META.get('REMOTE_ADDR')
        return remote_addr if remote_addr else 'UNKNOWN'

    except Exception as exc:
        logger.warning("Error extracting client IP: %s", exc)
        return 'UNKNOWN'


def _log_error(message: str, level: int = logging.ERROR,
               status_code: int = 500, exception=None) -> None:
    """
    Emit a structured log entry for security/audit trail purposes.

    Args:
        message:     Human-readable description of the event.
        level:       Python ``logging`` level constant (default ERROR).
        status_code: HTTP status code associated with this event.
        exception:   The original exception object (used for exc_info).
    """
    try:
        exc_context = (
            f" | Exception: {type(exception).__name__}: {exception}"
            if exception else ""
        )
        full_message = f"[{status_code}] {message}{exc_context}"

        if level == logging.ERROR:
            logger.error(full_message, exc_info=(exception is not None))
        elif level == logging.WARNING:
            logger.warning(full_message)
        elif level == logging.INFO:
            logger.info(full_message)
        else:
            logger.log(level, full_message)

    except Exception as log_exc:
        # Safeguard: never crash because of a logging failure
        logger.critical("Error during exception logging: %s", log_exc)


# =============================================================================
# LOCAL EXCEPTION HANDLER  (kept for backwards-compat; DRF REST_FRAMEWORK
# EXCEPTION_HANDLER setting should point to apps.common.exceptions instead)
# =============================================================================

def custom_exception_handler(exc, context):
    """
    Authentication-domain exception handler.

    .. important::

        The project-wide exception handler is configured in
        ``apps.common.exceptions.custom_exception_handler`` which already
        handles all auth exception types.  This function is preserved here
        so that any legacy ``REST_FRAMEWORK['EXCEPTION_HANDLER']`` pointer
        to this module continues to work.

    Intercepts and standardizes all exceptions into:

    .. code-block:: json

        {
            "success": false,
            "message": "Human-readable summary",
            "errors": { "...": "detailed error data" },
            "data": null
        }
    """
    try:
        view        = context.get('view')
        request     = context.get('request')
        view_name   = view.__class__.__name__ if view else 'UnknownView'
        method      = request.method if request else 'UNKNOWN'
        path        = request.path  if request else 'UNKNOWN'
        user_id     = (
            request.user.id
            if request and request.user and request.user.is_authenticated
            else 'ANONYMOUS'
        )
        ip_address  = _get_client_ip(request)

        # -- Call DRF's default handler first ----------------------------------
        response = drf_exception_handler(exc, context)

        if response is not None:
            error_data = (
                response.data
                if isinstance(response.data, dict)
                else {"detail": response.data}
            )
            message = error_data.get(
                "detail",
                error_data.get("non_field_errors", "An error occurred.")
            )
            if isinstance(message, list):
                message = message[0] if message else "An error occurred."

            # Special handling for Throttled
            if isinstance(exc, Throttled):
                response.data = {
                    "success": False,
                    "message": "Rate limit exceeded. Please try again later.",
                    "errors": {
                        "detail": str(exc.detail),
                        "retry_after": (
                            exc.wait() if hasattr(exc, 'wait') and callable(exc.wait) else 60
                        ),
                    },
                    "data": None,
                }
                _log_error(
                    f"⛔ RATE LIMIT EXCEEDED: {view_name} | IP: {ip_address} | User: {user_id}",
                    level=logging.WARNING,
                    status_code=response.status_code,
                    exception=exc,
                )
                return response

            response.data = {
                "success": False,
                "message": str(message),
                "errors": error_data,
                "data": None,
            }

            log_message = (
                f"⚠️  DRF Exception in {view_name} [{method} {path}] "
                f"| User: {user_id} | IP: {ip_address}"
            )
            level = logging.ERROR if response.status_code >= 500 else logging.WARNING
            _log_error(log_message, level=level, status_code=response.status_code, exception=exc)
            return response

        # -- Django / Python exceptions not handled by DRF --------------------
        error_response = {
            "success": False,
            "message": "An error occurred.",
            "errors": {},
            "data": None,
        }
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        log_level   = logging.ERROR

        if isinstance(exc, Http404):
            error_response["message"] = "Resource not found."
            http_status = status.HTTP_404_NOT_FOUND
            log_level   = logging.WARNING

        elif isinstance(exc, (PermissionDenied, DRFPermissionDenied)):
            error_response["message"] = "You do not have permission to access this resource."
            http_status = status.HTTP_403_FORBIDDEN
            log_level   = logging.WARNING

        elif isinstance(exc, (
            SoftDeletedUserError, AccountInactiveError, AccountDeactivatedError,
            AccountSuspendedError, InvalidCredentialsError, AuthenticationError,
            InvalidCredentialsException, AuthenticationException,
        )):
            error_response["message"] = (
                str(exc.detail) if hasattr(exc, 'detail') else "Authentication failed."
            )
            http_status = getattr(exc, 'status_code', status.HTTP_401_UNAUTHORIZED)
            log_level   = logging.WARNING

        elif isinstance(exc, DjangoValidationError):
            error_response["message"] = "Validation failed."
            error_response["errors"]  = (
                exc.message_dict if hasattr(exc, 'message_dict') else {"detail": str(exc)}
            )
            http_status = status.HTTP_400_BAD_REQUEST
            log_level   = logging.WARNING

        elif isinstance(exc, ValueError):
            error_response["message"] = str(exc)
            http_status = status.HTTP_400_BAD_REQUEST
            log_level   = logging.WARNING

        else:
            error_response["message"] = "Internal server error."

        if settings.DEBUG:
            error_response["debug_traceback"] = traceback.format_exc()

        log_message = (
            f"❌ Unhandled Exception in {view_name} [{method} {path}] "
            f"| User: {user_id} | IP: {ip_address} | Type: {type(exc).__name__}"
        )
        _log_error(log_message, level=log_level, status_code=http_status, exception=exc)
        return Response(error_response, status=http_status)

    except Exception as handler_exc:
        logger.critical(
            "🔥 CRITICAL: Auth exception handler failed! "
            "Original: %s: %s | Handler Error: %s",
            type(exc).__name__, exc, handler_exc,
            exc_info=True,
        )
        return Response(
            {
                "success": False,
                "message": "An unexpected error occurred. Please contact support.",
                "errors": {},
                "data": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
