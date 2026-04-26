# apps/common/views.py
"""
Common Infrastructure Views — System Health & Media Pipeline
===========================================================

Provides system-wide utility endpoints including asynchronous health checks
and a secure, HMAC-signed media upload pipeline (presigned tokens & webhooks).

Architecture:
  - Health: Asynchronous gather() for non-blocking latency measurement.
  - Upload: Two-step verification (HMAC presign -> Celery webhook processing).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.common.serializers import PresignRequestSerializer

logger = logging.getLogger(__name__)

# Track server start time for uptime calculation
_SERVER_START: float = time.monotonic()

# Simple version tag — update when you cut a release
API_VERSION: str = getattr(settings, "API_VERSION", "1.0.0")


# ===========================================================================
# ASYNC HEALTH CHECK HELPERS
# ===========================================================================


async def _acheck_database() -> dict[str, Any]:
    """Verify primary DB connection and measure round-trip latency (Async)."""
    def _do_check():
        t0 = time.monotonic()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {"status": "ok", "latency_ms": latency_ms}
        except Exception as exc:
            logger.error("Health check — database error: %s", exc)
            return {"status": "error", "error": str(exc)}
    return await asyncio.to_thread(_do_check)


async def _acheck_redis() -> dict[str, Any]:
    """Verify Redis PING latency (Async, fast-fail at 300ms)."""
    def _do_check():
        import redis as redis_lib
        t0 = time.monotonic()
        try:
            from django.conf import settings
            redis_url = getattr(settings, 'REDIS_URL', 'redis://127.0.0.1:6379/0')
            conn = redis_lib.from_url(
                redis_url,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
                decode_responses=True,
            )
            conn.ping()
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {"status": "ok", "latency_ms": latency_ms}
        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.warning("Health check — redis error: %s", exc)
            return {"status": "error", "error": str(exc), "latency_ms": latency_ms}
    return await asyncio.to_thread(_do_check)


async def _acheck_celery() -> dict[str, Any]:
    """Count active Celery workers via inspect interface."""
    def _do_check():
        try:
            from backend.celery import app as celery_app
            inspector = celery_app.control.inspect(timeout=0.3)
            stats = inspector.stats()
            if stats:
                worker_count = len(stats)
                return {"status": "ok", "workers": worker_count}
            return {"status": "warning", "workers": 0, "note": "No active workers found"}
        except Exception as exc:
            logger.warning("Health check — celery inspect failed: %s", exc)
            return {"status": "warning", "error": str(exc), "note": "Celery stats unavailable"}
    return await asyncio.to_thread(_do_check)


async def _acheck_migrations() -> dict[str, Any]:
    """Check for unapplied database migrations."""
    def _do_check():
        try:
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            pending = len(plan)
            if pending:
                return {"status": "warning", "pending": pending, "note": f"{pending} migrations not applied"}
            return {"status": "ok", "pending": 0}
        except Exception as exc:
            logger.warning("Health check — migrations check failed: %s", exc)
            return {"status": "warning", "error": str(exc)}
    return await asyncio.to_thread(_do_check)


async def _acheck_storage() -> dict[str, Any]:
    """Identify the configured storage/CDN provider."""
    try:
        default_storage = getattr(settings, "DEFAULT_FILE_STORAGE", "")
        if "cloudinary" in default_storage.lower():
            return {"status": "ok", "provider": "cloudinary"}
        if "s3" in default_storage.lower():
            return {"status": "ok", "provider": "s3"}
        return {"status": "ok", "provider": default_storage}
    except Exception as exc:
        return {"status": "warning", "error": str(exc)}


async def _acheck_email() -> dict[str, Any]:
    """Identify the configured email backend."""
    try:
        email_backend = getattr(settings, "EMAIL_BACKEND", "")
        if "anymail" in email_backend.lower():
            provider = getattr(settings, "ANYMAIL", {}).get("ESP_NAME", "anymail")
        elif "console" in email_backend.lower():
            provider = "console (dev mode)"
        else:
            provider = email_backend.split('.')[-1]
        return {"status": "ok", "provider": provider}
    except Exception as exc:
        return {"status": "warning", "error": str(exc)}


# ===========================================================================
# SYSTEM HEALTH ENDPOINT
# ===========================================================================


class HealthCheckView(View):
    """
    GET /api/health/ — System Vital Signs.

    Flow:
      1. Aggregates check results from DB, Redis, Celery, and Migrations.
      2. Uses asyncio.gather() for concurrent execution.
      3. Calculates server uptime and round-trip latency.

    Security:
      - Public endpoint (AllowAny equivalent via View).
      - Does not leak sensitive environment vars.

    Status Codes:
      - 200: Healthy or Warning (minor degradation).
      - 503: Degraded (critical dependency failure).
    """
    http_method_names = ["get", "head"]

    async def get(self, request: HttpRequest, *args: Any, **kwargs: Any):
        t0 = time.monotonic()
        db_res, redis_res, cel_res, mig_res, store_res, email_res = await asyncio.gather(
            _acheck_database(),
            _acheck_redis(),
            _acheck_celery(),
            _acheck_migrations(),
            _acheck_storage(),
            _acheck_email(),
            return_exceptions=True
        )

        def _safe_res(res: Any, fall: str) -> dict[str, Any]:
            return res if isinstance(res, dict) else {"status": fall, "error": str(res)}

        checks: dict[str, Any] = {
            "database":   _safe_res(db_res,    "error"),
            "redis":      _safe_res(redis_res, "error"),
            "celery":     _safe_res(cel_res,   "warning"),
            "migrations": _safe_res(mig_res,   "error"),
            "storage":    _safe_res(store_res, "warning"),
            "email":      _safe_res(email_res, "warning"),
        }

        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
        uptime_seconds = round(time.monotonic() - _SERVER_START)
        has_error = any(v.get("status") == "error" for v in checks.values())
        has_warning = any(v.get("status") == "warning" for v in checks.values())

        payload: dict[str, Any] = {
            "success":         not has_error,
            "status":          "degraded" if has_error else "warning" if has_warning else "healthy",
            "version":         API_VERSION,
            "timestamp":       datetime.now(tz=timezone.utc).isoformat(),
            "uptime_seconds":  uptime_seconds,
            "check_time_ms":   elapsed_ms,
            "checks":          checks,
        }

        return JsonResponse(payload, status=503 if has_error else 200)


# ===========================================================================
# CLOUDINARY MEDIA PIPELINE
# ===========================================================================


class CloudinaryPresignView(generics.GenericAPIView):
    """
    POST /api/v1/upload/presign/ — Secure Media Upload Authorization.

    Flow:
      1. Validates requested asset_type against system config.
      2. Generates time-limited HMAC-SHA256 signature via Cloudinary utility.
      3. Returns signed params for client-side direct upload.

    Security:
      - Requires IsAuthenticated.
      - Uses HMAC signature to prevent unauthorized bucket access.
      - Enforces user-specific folder paths in Cloudinary.

    Status Codes:
      - 200: Signature generated successfully.
      - 400: Invalid asset_type or missing data.
      - 500: Cloudinary configuration or signing error.
    """
    serializer_class = PresignRequestSerializer
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from apps.common.utils.cloudinary import generate_cloudinary_upload_params

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        asset_type = serializer.validated_data["asset_type"]
        context_id = request.data.get("context_id") or None

        result = generate_cloudinary_upload_params(
            user_id=str(request.user.pk),
            asset_type=asset_type,
            context_id=context_id,
        )

        if not result.success:
            return error_response(
                message="Could not generate upload token.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return success_response(
            data=result.to_dict(),
            message="Upload token generated successfully."
        )


@method_decorator(csrf_exempt, name="dispatch")
class CloudinaryWebhookView(View):
    """
    POST /api/v1/upload/webhook/cloudinary/ — Asynchronous Upload Confirmation.

    Flow:
      1. Receives notification from Cloudinary after successful direct upload.
      2. Validates X-Cld-Signature using shared secret.
      3. Dispatches Celery task to persist metadata to local DB.

    Security:
      - Exempt from CSRF (External Webhook).
      - MANDATORY signature validation to prevent spoofing.

    Status Codes:
      - 200: Always returned to Cloudinary to acknowledge receipt.
    """
    http_method_names = ["post", "head"]

    def post(self, request: HttpRequest) -> JsonResponse:
        from apps.common.tasks import process_cloudinary_upload_webhook
        from apps.common.utils.cloudinary import validate_cloudinary_webhook

        body = request.body
        timestamp = request.headers.get("X-Cld-Timestamp", "")
        signature = request.headers.get("X-Cld-Signature", "")

        if not validate_cloudinary_webhook(body, timestamp, signature):
            logger.warning("Cloudinary webhook: invalid signature.")
            return JsonResponse({"status": "rejected"}, status=200)

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"status": "parse_error"}, status=200)

        notification_type = payload.get("notification_type", "")
        secure_url = payload.get("secure_url", "")

        if notification_type in ("upload", "eager") and secure_url:
            process_cloudinary_upload_webhook.apply_async(
                kwargs={"payload": payload},
                ignore_result=True,
            )

        return JsonResponse({"status": "received"}, status=200)
