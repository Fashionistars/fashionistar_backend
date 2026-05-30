# apps/common/responses.py
"""
Unified API response rendering for Fashionistar.

ALL API responses — whether from Django Ninja or Django REST Framework —
follow the same JSON envelope:

    SUCCESS (2xx):
    {
        "success": true,
        "message": "Resource created successfully.",
        "data":    { ... } | [ ... ] | null,
        "meta":    { "request_id": "...", "version": "v2" }   ← optional
    }

    ERROR (4xx, 5xx):
    {
        "success": false,
        "message": "Validation failed.",
        "code":    "validation_error",
        "errors":  { "email": ["Enter a valid email address."] }
    }

Components
──────────
FashionistarRenderer  — DRF JSONRenderer subclass; wraps every response
                        automatically when registered in REST_FRAMEWORK settings.

success_response()    — Helper for DRF function-based views and Ninja endpoints
                        that want to build the envelope explicitly.

error_response()      — Helper for returning consistent error envelopes.

Registration in settings.py::

    REST_FRAMEWORK = {
        'DEFAULT_RENDERER_CLASSES': [
            'apps.common.renderers.FashionistarRenderer',
        ],
        ...
    }
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.http import JsonResponse
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Envelope builders (framework-agnostic)
# ---------------------------------------------------------------------------

def success_response(
    data: Any = None,
    *,
    message: str = "Request successful.",
    status: int = 200,
    meta: Optional[dict] = None,
) -> Response:
    """
    Build a standard DRF success Response.

    Args:
        data:    Serialised payload (dict, list, or None).
        message: Human-readable success message.
        status:  HTTP status code (default 200).
        meta:    Optional dict merged into the ``meta`` key
                 (request_id, version, timestamps, etc.).

    Returns:
        DRF Response with Fashionistar success envelope.

    Example::

        return success_response(
            data=serializer.data,
            message="User registered successfully.",
            status=201,
            meta={"request_id": request.request_id},
        )
    """
    payload: dict = {"success": True, "message": message, "data": data}
    if meta:
        payload["meta"] = meta
    return Response(payload, status=status)


def error_response(
    message: str = "An error occurred.",
    *,
    code: str = "error",
    errors: Any = None,
    status: int = 400,
    meta: Optional[dict] = None,
) -> Response:
    """
    Build a standard DRF error Response.

    Args:
        message: Human-readable error summary.
        code:    Machine-readable error code (for client switch-case).
        errors:  Detailed error map (field → messages) or list.
        status:  HTTP status code (default 400).
        meta:    Optional dict merged into the ``meta`` key.

    Returns:
        DRF Response with Fashionistar error envelope.

    Example::

        return error_response(
            message="Validation failed.",
            code="validation_error",
            errors=serializer.errors,
            status=422,
        )
    """
    payload: dict = {
        "success": False,
        "message": message,
        "code":    code,
    }
    if errors is not None:
        payload["errors"] = errors
    if meta:
        payload["meta"] = meta
    return Response(payload, status=status)


def ninja_success(
    data: Any = None,
    *,
    message: str = "Request successful.",
    meta: Optional[dict] = None,
) -> dict:
    """
    Build a plain dict success envelope for Django Ninja endpoints.
    Ninja serializes this directly to JSON.

    Example::

        @router.post('/auth/register')
        def register(request, payload: RegisterSchema):
            user = register_user(payload)
            return ninja_success(data=UserSchema.from_orm(user),
                                 message="Registered successfully.")
    """
    payload: dict = {"success": True, "message": message, "data": data}
    if meta:
        payload["meta"] = meta
    return payload


def ninja_error(
    message: str = "An error occurred.",
    *,
    code: str = "error",
    errors: Any = None,
    meta: Optional[dict] = None,
) -> dict:
    """
    Build a plain dict error envelope for Django Ninja endpoints.

    Example::

        from ninja.errors import HttpError

        @router.post('/auth/login')
        def login(request, payload: LoginSchema):
            user = authenticate_user(payload)
            if not user:
                raise HttpError(401, ninja_error("Invalid credentials.",
                                                 code="invalid_credentials"))
    """
    payload: dict = {"success": False, "message": message, "code": code}
    if errors is not None:
        payload["errors"] = errors
    if meta:
        payload["meta"] = meta
    return payload


def django_json_success(data: Any = None, *, message: str = "OK", status: int = 200) -> JsonResponse:
    """
    Plain Django JsonResponse success (for views that don't use DRF or Ninja).
    """
    return JsonResponse({"success": True, "message": message, "data": data}, status=status)


def django_json_error(message: str = "Error", *, code: str = "error", status: int = 400) -> JsonResponse:
    """
    Plain Django JsonResponse error (for views that don't use DRF or Ninja).
    """
    return JsonResponse({"success": False, "message": message, "code": code}, status=status)






__all__ = ["error_response", "success_response", "django_json_error", "django_json_success", "ninja_error", "ninja_success"] #added comment
