# apps/common/exceptions.py
"""
Global exception handling for the entire Fashionistar API surface.

Covers:
  - Django REST Framework exceptions (ValidationError, AuthenticationFailed, etc.)
  - Django core exceptions (Http404, PermissionDenied, ValidationError)
  - Django Ninja exceptions (via Ninja's own exception_handler decorator)
  - Completely unhandled Python exceptions (500)

All errors produce the same JSON envelope:

    {
        "success": false,
        "message": "Human-readable summary.",
        "code":    "machine_readable_code",
        "errors":  { "field": ["msg"] } | ["msg"] | null,
        "meta":    { "request_id": "...", "status": 422 }   ← optional
    }

Registration
────────────
DRF (in settings.py):
    REST_FRAMEWORK = {
        'EXCEPTION_HANDLER': 'apps.common.exceptions.custom_exception_handler',
    }

Django Ninja (in api router setup):
    from apps.common.exceptions import ninja_exception_handler
    api = NinjaAPI(...)
    api.exception_handler(Exception)(ninja_exception_handler)
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

# ---------------------------------------------------------------------------
# Error code mappings
# ---------------------------------------------------------------------------

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


def _build_error_payload(
    message: str,
    code: str,
    errors: Any = None,
    *,
    request_id: Optional[str] = None,
    http_status: Optional[int] = None,
) -> dict:
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


# ---------------------------------------------------------------------------
# DRF exception handler
# ---------------------------------------------------------------------------

def custom_exception_handler(exc: Exception, context: dict) -> Optional[Response]:
    """
    Global exception handler registered in REST_FRAMEWORK['EXCEPTION_HANDLER'].

    Handles:
    • All DRF APIException subclasses
    • Django Http404
    • Django PermissionDenied
    • Django ValidationError
    • Unhandled exceptions (→ 500)

    Args:
        exc:     The exception raised.
        context: DRF context dict containing 'request', 'view', etc.

    Returns:
        DRF Response with standardised Fashionistar error envelope,
        or None if the exception is not recognised (should not happen).
    """
    request_id = _get_request_id(context)

    # ── 1. Let DRF handle its own exceptions first ──────────────────────────
    response = exception_handler(exc, context)

    # ── 2. Django exceptions DRF does not handle ────────────────────────────
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
            payload = _build_error_payload(
                "You do not have permission to perform this action.",
                "permission_denied",
                request_id=request_id, http_status=403,
            )
            return Response(payload, status=status.HTTP_403_FORBIDDEN)

        # ── Truly unhandled: 500 ─────────────────────────────────────────
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

    # ── 3. Standardise DRF response ─────────────────────────────────────────
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

        # For Throttled: include wait time in message
        if isinstance(exc, Throttled) and exc.wait is not None:
            wait_secs = int(exc.wait) + 1
            message = f"Too many requests. Retry after {wait_secs} seconds."

        # Log 4xx/5xx security events
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


# ---------------------------------------------------------------------------
# Django Ninja exception handler
# ---------------------------------------------------------------------------

def ninja_exception_handler(request: HttpRequest, exc: Exception) -> JsonResponse:
    """
    Global exception handler for Django Ninja APIs.

    Register on the NinjaAPI instance::

        from apps.common.exceptions import ninja_exception_handler

        api = NinjaAPI(...)

        @api.exception_handler(Exception)
        def handle_all(request, exc):
            return ninja_exception_handler(request, exc)

    Args:
        request: Django HttpRequest.
        exc:     The exception raised inside a Ninja endpoint.

    Returns:
        JsonResponse with Fashionistar error envelope.
    """
    request_id: Optional[str] = getattr(request, "request_id", None)

    # ── Http404 ──────────────────────────────────────────────────────────────
    if isinstance(exc, Http404):
        payload = _build_error_payload(
            "The requested resource was not found.", "not_found",
            request_id=request_id, http_status=404,
        )
        return JsonResponse(payload, status=404)

    # ── Django PermissionDenied ───────────────────────────────────────────────
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

    # ── Django ValidationError ────────────────────────────────────────────────
    if isinstance(exc, DjangoValidationError):
        errors = (
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
        payload = _build_error_payload(
            "Validation failed.", "validation_error", errors,
            request_id=request_id, http_status=400,
        )
        return JsonResponse(payload, status=400)

    # ── Catch-all 500 ─────────────────────────────────────────────────────────
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