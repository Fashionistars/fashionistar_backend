# apps/common/exceptions.py
"""
Global exception handling for the entire Fashionistar API surface.

Architecture
────────────
This module has TWO responsibilities:

1. **Global error envelope** — every API error (DRF, Django, Ninja, or
   unhandled) is normalized into the same JSON shape:

       {
           "success": false,
           "message": "Human-readable summary.",
           "code":    "machine_readable_code",
           "errors":  { "field": ["msg"] } | ["msg"] | null,
           "meta":    { "request_id": "...", "status": 422 }
       }

2. **Auth-domain exception awareness** — the global DRF handler and
   Ninja handler are auth-exception-aware. They check for
   ``apps.authentication.exceptions.AuthenticationError`` subclasses
   BEFORE falling through to generic error mapping, so that typed
   errors like ``SoftDeletedUserError`` (403), ``DuplicateUserError``
   (409), and ``InvalidCredentialsError`` (401) produce the correct
   HTTP status codes and messages without any view-level boiler-plate.

Auth exceptions live in ``apps.authentication.exceptions``.
This file only *handles* them — it does not define them — keeping the
dependency direction clean (common ← authentication, not ← →).

Registration
────────────
DRF (settings.py):
    REST_FRAMEWORK = {
        'EXCEPTION_HANDLER': 'apps.common.exceptions.custom_exception_handler',
    }

Django Ninja (in api router setup):
    from apps.common.exceptions import ninja_exception_handler

    @api.exception_handler(Exception)
    def handle_all(request, exc):
        return ninja_exception_handler(request, exc)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.core.exceptions import (
    PermissionDenied as DjangoPermissionDenied,
)
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)
security_logger = logging.getLogger("security")


# ─────────────────────────────────────────────────────────────────────────────
# Error code mappings
# ─────────────────────────────────────────────────────────────────────────────

#: Maps DRF exception types → (code, human-readable message).
#: Checked in order; first match wins.
_EXCEPTION_CODE_MAP: dict[type, tuple[str, str]] = {
    ValidationError:       ("validation_error",        "Validation failed."),
    ParseError:            ("parse_error",             "Malformed request body."),
    AuthenticationFailed:  ("authentication_failed",   "Authentication failed."),
    NotAuthenticated:      ("not_authenticated",       "Authentication credentials were not provided."),
    PermissionDenied:      ("permission_denied",       "You do not have permission to perform this action."),
    NotFound:              ("not_found",               "The requested resource was not found."),
    MethodNotAllowed:      ("method_not_allowed",      "HTTP method not allowed."),
    UnsupportedMediaType:  ("unsupported_media_type",  "Unsupported media type."),
    Throttled:             ("throttled",               "Request was throttled. Please slow down."),
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_error_payload(
    message: str,
    code: str,
    errors: Any = None,
    *,
    request_id: Optional[str] = None,
    http_status: Optional[int] = None,
) -> dict:
    """Build the standard Fashionistar error envelope."""
    payload: dict = {
        "success": False,
        "message": message,
        "code":    code,
    }
    if errors is not None:
        payload["errors"] = errors
    meta: dict = {}
    if request_id:
        meta["request_id"] = request_id
    if http_status:
        meta["status"] = http_status
    if meta:
        payload["meta"] = meta
    return payload


def _get_request_id(context: Optional[dict]) -> Optional[str]:
    """Safely extract X-Request-ID from the DRF exception context."""
    try:
        return getattr(context.get("request"), "request_id", None)  # type: ignore[union-attr]
    except Exception:
        return None


def _load_auth_exception_base() -> Optional[type]:
    """
    Lazily import ``AuthenticationError`` from the authentication app.

    Returns None (instead of raising) if the auth app is not installed
    or during early boot — so this module stays importable everywhere.
    """
    try:
        from apps.authentication.exceptions import AuthenticationError
        return AuthenticationError
    except ImportError:
        return None


def _handle_auth_exception(
    exc: Exception,
    request_id: Optional[str],
) -> Optional[Response]:
    """
    Handle auth-domain exceptions (``AuthenticationError`` subclasses)
    and produce a properly-typed DRF Response.

    Returns None if ``exc`` is not an auth-domain exception.

    Auth exceptions (DuplicateUserError, SoftDeletedUserError, etc.) all
    inherit from DRF ``APIException`` via ``AuthenticationError``, so they
    carry their own ``status_code``, ``default_detail``, and
    ``default_code``.  We trust those values here.
    """
    AuthErr = _load_auth_exception_base()
    if AuthErr is None or not isinstance(exc, AuthErr):
        return None

    api_exc: APIException = exc  # type: ignore[assignment]
    http_status_code: int = api_exc.status_code
    code: str  = api_exc.default_code
    message: str = (
        api_exc.detail
        if isinstance(api_exc.detail, str)
        else str(api_exc.detail)
    )

    # Security logging for 401/403 events
    if http_status_code in (401, 403):
        security_logger.warning(
            "SECURITY_AUDIT action=AUTH_ERROR code=%s req=%s",
            code, request_id or "-",
        )

    payload = _build_error_payload(
        message, code, request_id=request_id, http_status=http_status_code,
    )
    return Response(payload, status=http_status_code)


def _handle_auth_exception_json(
    exc: Exception,
    request_id: Optional[str],
) -> Optional[JsonResponse]:
    """
    Same as ``_handle_auth_exception`` but returns ``JsonResponse``
    for use in the Django Ninja handler.
    """
    AuthErr = _load_auth_exception_base()
    if AuthErr is None or not isinstance(exc, AuthErr):
        return None

    api_exc: APIException = exc  # type: ignore[assignment]
    http_status_code: int = api_exc.status_code
    code: str = api_exc.default_code
    message: str = (
        api_exc.detail
        if isinstance(api_exc.detail, str)
        else str(api_exc.detail)
    )

    if http_status_code in (401, 403):
        security_logger.warning(
            "SECURITY_AUDIT action=AUTH_ERROR code=%s req=%s",
            code, request_id or "-",
        )

    payload = _build_error_payload(
        message, code, request_id=request_id, http_status=http_status_code,
    )
    return JsonResponse(payload, status=http_status_code)


# ─────────────────────────────────────────────────────────────────────────────
# DRF global exception handler
# ─────────────────────────────────────────────────────────────────────────────

def custom_exception_handler(exc: Exception, context: dict) -> Optional[Response]:
    """
    Global exception handler for Django REST Framework.

    Register in settings.py::

        REST_FRAMEWORK = {
            'EXCEPTION_HANDLER': 'apps.common.exceptions.custom_exception_handler',
        }

    Handles (in priority order):
    ①  Auth-domain exceptions (``AuthenticationError`` subclasses):
        DuplicateUserError, SoftDeletedUserError, AccountInactiveError,
        InvalidCredentialsError, SoftDeletedUserExistsError, etc.
        → Translated using the exception's own status_code / default_code.

    ②  All DRF ``APIException`` subclasses (ValidationError, NotFound, etc.)
        → Normalized via ``_EXCEPTION_CODE_MAP``.

    ③  Django core exceptions (Http404, PermissionDenied, ValidationError)
        → Manually translated.

    ④  Truly unhandled Python exceptions → 500 Server Error.

    Args:
        exc:     The exception raised inside a DRF view or serializer.
        context: DRF context dict (contains 'request', 'view', etc.).

    Returns:
        Standardized Fashionistar error Response, never None.
    """
    request_id = _get_request_id(context)

    # ── ① Auth-domain exception (highest priority) ───────────────────────────
    auth_response = _handle_auth_exception(exc, request_id)
    if auth_response is not None:
        return auth_response

    # ── ② Standard DRF exception handling ───────────────────────────────────
    response = exception_handler(exc, context)

    # ── ③ Django exceptions DRF does not convert ────────────────────────────
    if response is None:
        if isinstance(exc, DjangoValidationError):
            errors = (
                exc.message_dict
                if hasattr(exc, "message_dict")
                else exc.messages
            )
            payload = _build_error_payload(
                "Validation failed.", "validation_error", errors,
                request_id=request_id, http_status=400,
            )
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, Http404):
            payload = _build_error_payload(
                "The requested resource was not found.", "not_found",
                request_id=request_id, http_status=404,
            )
            return Response(payload, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, DjangoPermissionDenied):
            security_logger.warning(
                "SECURITY_AUDIT action=PERMISSION_DENIED req=%s",
                request_id or "-",
            )
            payload = _build_error_payload(
                "You do not have permission to perform this action.",
                "permission_denied",
                request_id=request_id, http_status=403,
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        # ── ④ Truly unhandled: 500 ────────────────────────────────────────
        logger.error(
            "Unhandled exception in API: %s", exc,
            exc_info=True, extra={"request_id": request_id},
        )
        security_logger.error(
            "SECURITY_AUDIT action=SERVER_ERROR req=%s error=%r",
            request_id or "-", str(exc),
        )
        payload = _build_error_payload(
            "An unexpected server error occurred. Our team has been notified.",
            "server_error",
            request_id=request_id, http_status=500,
        )
        return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ── Normalize the DRF response into the standard envelope ────────────────
    if response is not None:
        http_status_code: int = response.status_code

        # Already wrapped — pass through
        if isinstance(response.data, dict) and "success" in response.data:
            return response

        # Map exception type → (code, message)
        message = "Request failed."
        code = "error"
        for exc_type, (exc_code, exc_message) in _EXCEPTION_CODE_MAP.items():
            if isinstance(exc, exc_type):
                code = exc_code
                message = exc_message
                break

        # For Throttled: include wait time in message AND set Retry-After HTTP header
        # RFC 7231 §7.1.3 — clients MUST respect Retry-After on 429 responses.
        if isinstance(exc, Throttled) and exc.wait is not None:
            wait_secs = int(exc.wait) + 1
            message = f"Too many requests. Retry after {wait_secs} seconds."
            response["Retry-After"] = str(wait_secs)

        # Security event logging
        if http_status_code in (401, 403):
            security_logger.warning(
                "SECURITY_AUDIT action=PERMISSION_DENIED req=%s code=%s",
                request_id or "-", code,
            )
        elif http_status_code >= 500:
            logger.error(
                "API 5xx error req=%s code=%s exc=%r",
                request_id or "-", code, exc,
            )

        response.data = _build_error_payload(
            message, code, response.data,
            request_id=request_id, http_status=http_status_code,
        )

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Django Ninja global exception handler
# ─────────────────────────────────────────────────────────────────────────────

def ninja_exception_handler(request: HttpRequest, exc: Exception) -> JsonResponse:
    """
    Global exception handler for Django Ninja APIs.

    Register on the NinjaAPI instance::

        from apps.common.exceptions import ninja_exception_handler

        api = NinjaAPI(...)

        @api.exception_handler(Exception)
        def handle_all(request, exc):
            return ninja_exception_handler(request, exc)

    Handles (in priority order):
    ①  Auth-domain exceptions → typed HTTP status from exception.status_code
    ②  Http404              → 404
    ③  Django PermissionDenied → 403
    ④  Django ValidationError  → 400
    ⑤  Catch-all              → 500

    Args:
        request: Django HttpRequest.
        exc:     The exception raised inside a Ninja endpoint.

    Returns:
        JsonResponse with the Fashionistar error envelope.
    """
    request_id: Optional[str] = getattr(request, "request_id", None)

    # ── ① Auth-domain exception ──────────────────────────────────────────────
    auth_json = _handle_auth_exception_json(exc, request_id)
    if auth_json is not None:
        return auth_json

    # ── ② Http404 ────────────────────────────────────────────────────────────
    if isinstance(exc, Http404):
        payload = _build_error_payload(
            "The requested resource was not found.", "not_found",
            request_id=request_id, http_status=404,
        )
        return JsonResponse(payload, status=404)

    # ── ③ Django PermissionDenied ────────────────────────────────────────────
    if isinstance(exc, DjangoPermissionDenied):
        security_logger.warning(
            "SECURITY_AUDIT action=PERMISSION_DENIED req=%s",
            request_id or "-",
        )
        payload = _build_error_payload(
            "You do not have permission to perform this action.",
            "permission_denied",
            request_id=request_id, http_status=403,
        )
        return JsonResponse(payload, status=403)

    # ── ④ Django ValidationError ─────────────────────────────────────────────
    if isinstance(exc, DjangoValidationError):
        errors = (
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
        payload = _build_error_payload(
            "Validation failed.", "validation_error", errors,
            request_id=request_id, http_status=400,
        )
        return JsonResponse(payload, status=400)

    # ── ⑤ Catch-all 500 ──────────────────────────────────────────────────────
    logger.error(
        "Unhandled Ninja exception: %s", exc,
        exc_info=True, extra={"request_id": request_id},
    )
    security_logger.error(
        "SECURITY_AUDIT action=SERVER_ERROR req=%s error=%r",
        request_id or "-", str(exc),
    )
    payload = _build_error_payload(
        "An unexpected server error occurred. Our team has been notified.",
        "server_error",
        request_id=request_id, http_status=500,
    )
    return JsonResponse(payload, status=500)