# apps/authentication/exceptions.py
"""
Advanced Exception Handling Framework for Authentication API.

This module provides:
1. Custom Exception Classes: Tailored for authentication-specific errors.
2. Global Exception Handler: Intercepts DRF, Django, and Python exceptions.
3. Standardized JSON Responses: All errors return {success, message, errors, data} structure.
4. Audit Logging: Full context logging for security events (4xx/5xx errors).
5. Rate Limit Handling: Custom response for throttled requests.
"""

import logging
import traceback
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import (
    ValidationError as DRFValidationError,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied as DRFPermissionDenied,
    NotFound,
    MethodNotAllowed,
    NotAcceptable,
    Throttled,
    ParseError,
    UnsupportedMediaType,
    APIException
)

# Initialize Logger for Authentication Events
logger = logging.getLogger('application')


# ============================================================================
# CUSTOM EXCEPTION CLASSES
# ============================================================================

class AuthenticationException(APIException):
    """
    Base exception for authentication-related errors.
    HTTP Status: 401 Unauthorized
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Authentication failed."
    default_code = "authentication_failed"


class InvalidCredentialsException(AuthenticationException):
    """
    Raised when email/phone and password do not match.
    """
    default_detail = "Invalid email/phone or password."
    default_code = "invalid_credentials"


class AccountNotVerifiedException(AuthenticationException):
    """
    Raised when user attempts to login but account is not verified.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Account not verified. Please verify your email/phone."
    default_code = "account_not_verified"


class OTPExpiredException(AuthenticationException):
    """
    Raised when user provides expired OTP.
    """
    default_detail = "OTP has expired. Please request a new one."
    default_code = "otp_expired"


class InvalidOTPException(AuthenticationException):
    """
    Raised when OTP doesn't match.
    """
    default_detail = "Incorrect OTP. Please try again."
    default_code = "invalid_otp"


class RateLimitExceededException(APIException):
    """
    Custom Rate Limit Exception (replaces default Throttled).
    HTTP Status: 429 Too Many Requests
    """
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Too many requests. Please try again later."
    default_code = "rate_limit_exceeded"


# ============================================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================================

def custom_exception_handler(exc, context):
    """
    Industrial-Grade Exception Handler.

    Intercepts and standardizes all exceptions (DRF, Django, Python) into:
    {
        "success": false,
        "message": "Human-readable summary",
        "errors": { ... detailed error data ... },
        "data": null
    }
    """
    try:
        # ====================================================================
        # 1. GET CONTEXT INFORMATION FOR LOGGING
        # ====================================================================
        view = context.get('view')
        request = context.get('request')
        
        view_name = view.__class__.__name__ if view else 'UnknownView'
        method = request.method if request else 'UNKNOWN'
        path = request.path if request else 'UNKNOWN'
        user_id = request.user.id if request and request.user and request.user.is_authenticated else 'ANONYMOUS'
        ip_address = _get_client_ip(request) if request else 'UNKNOWN'

        # ====================================================================
        # 2. CALL DRF'S DEFAULT EXCEPTION HANDLER
        # ====================================================================
        # This handles DRF-specific exceptions (ValidationError, PermissionDenied, etc.)
        response = drf_exception_handler(exc, context)

        # ====================================================================
        # 3. BUILD STANDARDIZED ERROR RESPONSE
        # ====================================================================
        if response is not None:
            # DRF handled the exception, now standardize the format
            error_data = response.data if isinstance(response.data, dict) else {"detail": response.data}
            
            # Extract message or use default
            message = error_data.get("detail", error_data.get("non_field_errors", "An error occurred."))
            if isinstance(message, list):
                message = message[0] if message else "An error occurred."

            # Special handling for Throttled exceptions
            if isinstance(exc, Throttled):
                response.data = {
                    "success": False,
                    "message": "Rate limit exceeded. Please try again later.",
                    "errors": {
                        "detail": str(exc.detail),
                        "retry_after": exc.wait() if hasattr(exc, 'wait') and callable(exc.wait) else 60
                    },
                    "data": None
                }
                _log_error(
                    f"⛔ RATE LIMIT EXCEEDED: {view_name} | IP: {ip_address} | User: {user_id}",
                    level=logging.WARNING,
                    status_code=response.status_code,
                    exception=exc
                )
                return response

            # Standardize response format
            response.data = {
                "success": False,
                "message": str(message),
                "errors": error_data,
                "data": None
            }

            # ================================================================
            # LOG THE ERROR (DRF handled)
            # ================================================================
            log_message = f"⚠️  DRF Exception in {view_name} [{method} {path}] | User: {user_id} | IP: {ip_address}"
            
            if response.status_code >= 500:
                _log_error(log_message, level=logging.ERROR, status_code=response.status_code, exception=exc)
            else:
                _log_error(log_message, level=logging.WARNING, status_code=response.status_code, exception=exc)

            return response

        # ====================================================================
        # 4. HANDLE EXCEPTIONS NOT CAUGHT BY DRF
        # ====================================================================
        # Django or Python exceptions

        error_response = {
            "success": False,
            "message": "An error occurred.",
            "errors": {},
            "data": None
        }
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        log_level = logging.ERROR

        # Specific exception types
        if isinstance(exc, Http404):
            error_response["message"] = "Resource not found."
            http_status = status.HTTP_404_NOT_FOUND
            log_level = logging.WARNING

        elif isinstance(exc, (PermissionDenied, DRFPermissionDenied)):
            error_response["message"] = "You do not have permission to access this resource."
            http_status = status.HTTP_403_FORBIDDEN
            log_level = logging.WARNING

        elif isinstance(exc, (InvalidCredentialsException, AuthenticationException)):
            error_response["message"] = str(exc.detail) if hasattr(exc, 'detail') else "Authentication failed."
            http_status = status.HTTP_401_UNAUTHORIZED
            log_level = logging.WARNING

        elif isinstance(exc, DjangoValidationError):
            error_response["message"] = "Validation failed."
            error_response["errors"] = exc.message_dict if hasattr(exc, 'message_dict') else {"detail": str(exc)}
            http_status = status.HTTP_400_BAD_REQUEST
            log_level = logging.WARNING

        elif isinstance(exc, ValueError):
            error_response["message"] = str(exc)
            http_status = status.HTTP_400_BAD_REQUEST
            log_level = logging.WARNING

        else:
            # Generic 500 error
            error_response["message"] = "Internal server error."
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

        # Include traceback in DEBUG mode
        if settings.DEBUG:
            error_response["debug_traceback"] = traceback.format_exc()

        # ====================================================================
        # LOG THE ERROR (Unhandled)
        # ====================================================================
        log_message = f"❌ Unhandled Exception in {view_name} [{method} {path}] | User: {user_id} | IP: {ip_address} | Type: {type(exc).__name__}"
        _log_error(log_message, level=log_level, status_code=http_status, exception=exc)

        # Return standardized response
        response = Response(error_response, status=http_status)
        return response

    except Exception as handler_exc:
        """
        Fallback: If the exception handler itself fails, return a safe 500 response.
        This prevents cascading failures.
        """
        logger.critical(
            f"🔥 CRITICAL: Exception handler itself failed! Original: {type(exc).__name__}: {str(exc)} | Handler Error: {str(handler_exc)}",
            exc_info=True
        )
        
        safe_response = {
            "success": False,
            "message": "An unexpected error occurred. Please contact support.",
            "errors": {},
            "data": None
        }
        return Response(safe_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_client_ip(request):
    """
    Extract client IP from request, accounting for proxies.
    """
    try:
        if request is None:
            return 'UNKNOWN'

        # Check for X-Forwarded-For (first IP in chain is original client)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()

        # Check for X-Real-IP
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip

        # Direct connection
        remote_addr = request.META.get('REMOTE_ADDR')
        return remote_addr if remote_addr else 'UNKNOWN'

    except Exception as e:
        logger.warning(f"Error extracting client IP: {str(e)}")
        return 'UNKNOWN'


def _log_error(message, level=logging.ERROR, status_code=500, exception=None):
    """
    Logs error with structured context for audit trail.
    """
    try:
        # Include exception type and message
        exc_context = f" | Exception: {type(exception).__name__}: {str(exception)}" if exception else ""
        full_message = f"[{status_code}] {message}{exc_context}"

        if level == logging.ERROR:
            logger.error(full_message, exc_info=(exception is not None))
        elif level == logging.WARNING:
            logger.warning(full_message)
        elif level == logging.INFO:
            logger.info(full_message)
        else:
            logger.log(level, full_message)

    except Exception as e:
        # Safeguard: If logging fails, don't crash
        logger.critical(f"Error during exception logging: {str(e)}")
