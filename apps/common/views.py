# apps/common/views.py
"""
Enterprise views for the Fashionistar common app.

Endpoints:
    GET  /api/health/                          — Health check (no auth)
    POST /api/v1/upload/presign/               — Cloudinary presign token (JWT auth)
    POST /api/v1/upload/webhook/cloudinary/    — Cloudinary notification receiver (no auth, HMAC validated)

Response structure:

    200 OK — all checks pass:
    {
        "success": true,
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": "2026-02-28T13:41:09+01:00",
        "request_id": "uuid4",
        "uptime_seconds": 3721,
        "checks": {
            "database":    {"status": "ok",       "latency_ms": 4.2},
            "redis":       {"status": "ok",       "latency_ms": 1.1},
            "celery":      {"status": "ok",       "workers": 2},
            "storage":     {"status": "ok",       "provider": "cloudinary"},
            "email":       {"status": "ok",       "provider": "zoho"},
            "migrations":  {"status": "ok",       "pending": 0}
        }
    }

    503 Service Unavailable — one or more checks fail:
    {
        "success": false,
        "status": "degraded",
        ...
        "checks": {
            "database": {"status": "error", "error": "connection refused"},
            ...
        }
    }

Metrics compatible with:
  - AWS ELB / ALB target health checks
  - Render.com /health/ pings (keep-alive for free tier)
  - Kubernetes liveness / readiness probes
  - Prometheus exporter (status exposed as gauge)
  - Uptime Robot / BetterUptime / Pingdom
  - Sentry performance monitoring (via request_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.common.serializers import PresignRequestSerializer
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import (
    BrowsableAPIRenderer,
    MultiPartRenderer,
    JSONRenderer,
    StaticHTMLRenderer,
)
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# Track server start time for uptime calculation
_SERVER_START: float = time.monotonic()

# Simple version tag — update when you cut a release
API_VERSION: str = getattr(settings, "API_VERSION", "1.0.0")


# ---------------------------------------------------------------------------
# Individual sub-checks
# ---------------------------------------------------------------------------


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
        except Exception as exc:  # noqa: BLE001
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

            redis_url = getattr(settings, "REDIS_URL", "redis://127.0.0.1:6379/0")
            # 300ms hard timeout — never hang for more than 300ms
            conn = redis_lib.from_url(
                redis_url,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
                decode_responses=True,
            )
            conn.ping()
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {"status": "ok", "latency_ms": latency_ms}
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.warning("Health check — redis error: %s", exc)
            return {"status": "error", "error": str(exc), "latency_ms": latency_ms}

    return await asyncio.to_thread(_do_check)


async def _acheck_celery() -> dict[str, Any]:
    """
    Count active Celery workers via Celery's inspect interface (Async).
    Falls back gracefully if broker is unavailable.
    """

    def _do_check():
        try:
            from backend.celery import app as celery_app

            inspector = celery_app.control.inspect(timeout=0.3)
            stats = inspector.stats()
            if stats:
                worker_count = len(stats)
                return {"status": "ok", "workers": worker_count}
            return {
                "status": "warning",
                "workers": 0,
                "note": "No active workers found",
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Health check — celery inspect failed: %s", exc)
            return {
                "status": "warning",
                "error": str(exc),
                "note": "Celery stats unavailable",
            }

    return await asyncio.to_thread(_do_check)


async def _acheck_migrations() -> dict[str, Any]:
    """Check for unapplied database migrations (Async)."""

    def _do_check():
        try:
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            pending = len(plan)
            if pending:
                return {
                    "status": "warning",
                    "pending": pending,
                    "note": f"{pending} migrations not applied",
                }
            return {"status": "ok", "pending": 0}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Health check — migrations check failed: %s", exc)
            return {"status": "warning", "error": str(exc)}

    return await asyncio.to_thread(_do_check)


async def _acheck_storage() -> dict[str, Any]:
    """Identify the configured storage/CDN provider (Non-blocking)."""
    try:
        default_storage = getattr(settings, "DEFAULT_FILE_STORAGE", "")
        if "cloudinary" in default_storage.lower():
            return {"status": "ok", "provider": "cloudinary"}
        if "s3" in default_storage.lower():
            return {"status": "ok", "provider": "s3"}
        return {"status": "ok", "provider": default_storage}
    except Exception as exc:  # noqa: BLE001
        return {"status": "warning", "error": str(exc)}


async def _acheck_email() -> dict[str, Any]:
    """Identify the configured email backend/provider (Non-blocking)."""
    try:
        email_backend = getattr(settings, "EMAIL_BACKEND", "")
        if "anymail" in email_backend.lower():
            provider = getattr(settings, "ANYMAIL", {}).get("ESP_NAME", "anymail")
        elif "console" in email_backend.lower():
            return {"status": "ok", "provider": "console (dev mode)"}
        else:
            provider = email_backend
        return {"status": "ok", "provider": provider}
    except Exception as exc:  # noqa: BLE001
        return {"status": "warning", "error": str(exc)}


# ---------------------------------------------------------------------------
# Health view
# ---------------------------------------------------------------------------


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

        # Gather all checks concurrently to minimize overall latency
        db_res, redis_res, cel_res, mig_res, store_res, email_res = (
            await asyncio.gather(
                _acheck_database(),
                _acheck_redis(),
                _acheck_celery(),
                _acheck_migrations(),
                _acheck_storage(),
                _acheck_email(),
                return_exceptions=True,
            )
        )

        def _safe_res(res: Any, fall: str) -> dict[str, Any]:
            return res if isinstance(res, dict) else {"status": fall, "error": str(res)}

        # Handle potential asyncio exceptions by converting to error dicts
        checks: dict[str, Any] = {
            "database": _safe_res(db_res, "error"),
            "redis": _safe_res(redis_res, "error"),
            "celery": _safe_res(cel_res, "warning"),
            "migrations": _safe_res(mig_res, "error"),
            "storage": _safe_res(store_res, "warning"),
            "email": _safe_res(email_res, "warning"),
        }

        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
        uptime_seconds = round(time.monotonic() - _SERVER_START)

        # Aggregate: any "error" → degraded
        has_error = any(v.get("status") == "error" for v in checks.values())
        has_warning = any(v.get("status") == "warning" for v in checks.values())

        overall_status = (
            "degraded" if has_error else "warning" if has_warning else "healthy"
        )

        request_id = getattr(request, "request_id", None)

        payload: dict[str, Any] = {
            "success": not has_error,
            "status": overall_status,
            "version": API_VERSION,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "uptime_seconds": uptime_seconds,
            "check_time_ms": elapsed_ms,
            "checks": checks,
        }
        if request_id:
            payload["request_id"] = request_id

        http_status = 503 if has_error else 200

        if has_error:
            logger.error(
                "Health check DEGRADED — failed checks: %s",
                [k for k, v in checks.items() if v.get("status") == "error"],
            )
        elif has_warning:
            logger.warning(
                "Health check WARNING — degraded checks: %s",
                [k for k, v in checks.items() if v.get("status") == "warning"],
            )

        return JsonResponse(payload, status=http_status)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cloudinary Pre-sign Endpoint
# POST /api/v1/upload/presign/
# ─────────────────────────────────────────────────────────────────────────────


def _get_valid_asset_types() -> frozenset:
    """Derive valid asset types from _ASSET_CONFIGS at import time."""
    try:
        from apps.common.utils.cloudinary import _ASSET_CONFIGS

        return frozenset(_ASSET_CONFIGS.keys())
    except Exception:
        return frozenset()


VALID_ASSET_TYPES = _get_valid_asset_types()


class CloudinaryPresignView(generics.GenericAPIView):
    """
    POST /api/v1/upload/presign/

    Generate a time-limited, HMAC-SHA256–signed Cloudinary upload token.
    The frontend uses this to POST a file DIRECTLY to Cloudinary without
    routing the upload data through the Django server.

    Authentication: Bearer JWT (IsAuthenticated).

    Request body (validated by PresignRequestSerializer):
        { "asset_type": "avatar" | "product_image" | "product_video" | "measurement" }

    Response 200:
        {
            "success":        true,
            "cloud_name":     "your_cloud",
            "api_key":        "...",
            "signature":      "hex-sha256",
            "timestamp":      1712345678,
            "folder":         "fashionistar/users/avatars/user_UUID",
            "upload_preset":  "fashionistar_avatars",
            "resource_type":  "image",
            "eager":          [...],
            "eager_async":    true
        }

    Response 400 — invalid asset_type (serializer validation error).
    Response 500 — signature generation failed.
    """

    serializer_class = PresignRequestSerializer
    permission_classes = [IsAuthenticated]
    renderer_classes = [
        CustomJSONRenderer,
        BrowsableAPIRenderer,
        MultiPartRenderer,
        JSONRenderer,
        StaticHTMLRenderer,
    ]

    def post(self, request: HttpRequest, *args, **kwargs):
        from apps.common.utils.cloudinary import generate_cloudinary_upload_params

        # ── Validate input via dedicated serializer ────────────────────────
        serializer = PresignRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset_type = serializer.validated_data["asset_type"]
        # Optional context_id: used by vendors to get unique presign params per product
        # when uploading bulk products rapidly. Avatar uploads don't need this.
        context_id = request.data.get("context_id") or None

        result = generate_cloudinary_upload_params(
            user_id=str(request.user.pk),
            asset_type=asset_type,
            context_id=context_id,
        )

        if not result.success:
            logger.error(
                "Presign generation failed for user=%s asset=%s: %s",
                request.user.pk,
                asset_type,
                result.error,
            )
            return error_response(
                message="Could not generate upload token. Please try again later.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            "Presign issued: user=%s asset=%s context_id=%s folder=%s",
            request.user.pk,
            asset_type,
            context_id,
            result.upload_params.get("folder"),
        )

        return success_response(
            data=result.to_dict(), message="Upload token generated successfully."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cloudinary Webhook Receiver
# POST /api/v1/upload/webhook/cloudinary/
# ─────────────────────────────────────────────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class CloudinaryWebhookView(View):
    """
    POST /api/v1/upload/webhook/cloudinary/ — Asynchronous Upload Confirmation.

    Flow:
      1. Receives notification from Cloudinary after successful direct upload.
      2. Validates X-Cld-Signature using shared secret.
      3. Dispatches Celery task to persist metadata to local DB.

    Receives Cloudinary notification_url callbacks after a successful upload
    (or eager transformation completion).  The payload contains the full asset
    metadata including ``public_id``, ``secure_url``, ``width``, ``height``,
    and ``eager`` transformation results.

    Security:
        - SHA1 signature validated against ``X-Cld-Signature`` +
          ``X-Cld-Timestamp`` headers before any processing.
        - Algorithm: SHA1(body + timestamp + api_secret)
        - CSRF exempt — Cloudinary is an external service; no CSRF cookie.
        - Always returns 200 to Cloudinary even on validation failure (to
          prevent Cloudinary from endlessly retrying).

    On valid payload:
        Dispatches a Celery task to update the appropriate model field with
        the ``secure_url`` from Cloudinary.
    """

    http_method_names = ["post", "head"]

    def post(self, request: HttpRequest) -> JsonResponse:  # type: ignore[override]
        from apps.common.tasks import process_cloudinary_upload_webhook
        from apps.common.utils.cloudinary import validate_cloudinary_webhook

        body = request.body
        timestamp = request.headers.get("X-Cld-Timestamp", "")
        signature = request.headers.get("X-Cld-Signature", "")

        # ── Validate signature ────────────────────────────────────────────
        if not validate_cloudinary_webhook(body, timestamp, signature):
            logger.warning(
                "Cloudinary webhook: invalid signature — rejected. "
                "timestamp=%s sig=%s",
                timestamp,
                signature[:16] if signature else "(none)",
            )
            # Return 200 to prevent Cloudinary retry storms
            return JsonResponse({"status": "rejected"}, status=200)

        # ── Parse payload ─────────────────────────────────────────────────
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Cloudinary webhook: JSON parse error: %s", exc)
            return JsonResponse({"status": "parse_error"}, status=200)

        notification_type = payload.get("notification_type", "")
        public_id = payload.get("public_id", "")
        secure_url = payload.get("secure_url", "")

        logger.info(
            "Cloudinary webhook received: type=%s public_id=%s url=%s",
            notification_type,
            public_id,
            secure_url[:60] if secure_url else "(none)",
        )

        # ── Dispatch background task ──────────────────────────────────────
        if notification_type in ("upload", "eager") and secure_url:
            try:
                process_cloudinary_upload_webhook.apply_async(
                    kwargs={"payload": payload},
                    ignore_result=True,
                )
            except Exception as exc:
                logger.error(
                    "Cloudinary webhook: failed to dispatch Celery task: %s",
                    exc,
                )
                # Still return 200 — we log it, but don't want Cloudinary to retry

        return JsonResponse({"status": "received"}, status=200)
