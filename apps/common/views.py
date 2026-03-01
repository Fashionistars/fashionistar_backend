# apps/common/views.py
"""
Enterprise Health-Check endpoint for the Fashionistar backend.

Endpoint:   GET /api/health/
Auth:       None required (used by load balancers & uptime monitors)
Caching:    Max 10 seconds (avoid hammering DB on every LB heartbeat)

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

import logging
import time
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.db import connection
from django.views import View
from django.http import HttpRequest

from apps.common.renderers import django_json_success, django_json_error

logger = logging.getLogger("application")

# Track server start time for uptime calculation
_SERVER_START: float = time.monotonic()

# Simple version tag — update when you cut a release
API_VERSION: str = getattr(settings, "API_VERSION", "2.0.0")


# ---------------------------------------------------------------------------
# Individual sub-checks
# ---------------------------------------------------------------------------

def _check_database() -> dict[str, Any]:
    """Verify primary DB connection and measure round-trip latency."""
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


def _check_redis() -> dict[str, Any]:
    """Verify Redis connection and measure PING latency."""
    try:
        from apps.common.utils import get_redis_connection_safe
        t0 = time.monotonic()
        conn = get_redis_connection_safe(max_retries=1, retry_delay=0)
        if conn is None:
            return {"status": "error", "error": "Unable to connect to Redis"}
        conn.ping()
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001
        logger.error("Health check — redis error: %s", exc)
        return {"status": "error", "error": str(exc)}


def _check_celery() -> dict[str, Any]:
    """
    Count active Celery workers via Celery's inspect interface.
    Falls back gracefully if broker is unavailable.
    """
    try:
        from backend.celery import app as celery_app
        inspector = celery_app.control.inspect(timeout=1.0)
        stats = inspector.stats()
        if stats:
            worker_count = len(stats)
            return {"status": "ok", "workers": worker_count}
        return {"status": "warning", "workers": 0, "note": "No active workers found"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check — celery inspect failed: %s", exc)
        return {"status": "warning", "error": str(exc), "note": "Celery stats unavailable"}


def _check_migrations() -> dict[str, Any]:
    """Check for unapplied database migrations."""
    try:
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        pending = len(plan)
        if pending:
            return {"status": "warning", "pending": pending,
                    "note": f"{pending} migration(s) not applied"}
        return {"status": "ok", "pending": 0}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check — migrations check failed: %s", exc)
        return {"status": "warning", "error": str(exc)}


def _check_storage() -> dict[str, Any]:
    """Identify the configured storage/CDN provider."""
    try:
        default_storage = getattr(settings, "DEFAULT_FILE_STORAGE", "")
        if "cloudinary" in default_storage.lower():
            return {"status": "ok", "provider": "cloudinary"}
        if "s3" in default_storage.lower():
            return {"status": "ok", "provider": "s3"}
        return {"status": "ok", "provider": default_storage}
    except Exception as exc:  # noqa: BLE001
        return {"status": "warning", "error": str(exc)}


def _check_email() -> dict[str, Any]:
    """Identify the configured email backend/provider."""
    try:
        email_backend = getattr(settings, "EMAIL_BACKEND", "")
        if "anymail" in email_backend.lower():
            provider = getattr(settings, "ANYMAIL", {}).get("ESP_NAME", "anymail")
        elif "mailgun" in email_backend.lower():
            provider = "mailgun"
        elif "zoho" in email_backend.lower():
            provider = "zoho"
        elif "smtp" in email_backend.lower():
            provider = "smtp"
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
    GET /api/health/
    Executes all sub-checks and returns aggregated health status.
    Safe for unauthenticated access (load balancers, uptime monitors).
    """

    http_method_names = ["get", "head"]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any):
        t0 = time.monotonic()

        checks: dict[str, Any] = {
            "database":   _check_database(),
            "redis":      _check_redis(),
            "celery":     _check_celery(),
            "migrations": _check_migrations(),
            "storage":    _check_storage(),
            "email":      _check_email(),
        }

        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
        uptime_seconds = round(time.monotonic() - _SERVER_START)

        # Aggregate: any "error" → degraded
        has_error = any(
            v.get("status") == "error"
            for v in checks.values()
        )
        has_warning = any(
            v.get("status") == "warning"
            for v in checks.values()
        )

        overall_status = (
            "degraded"  if has_error
            else "warning" if has_warning
            else "healthy"
        )

        request_id = getattr(request, "request_id", None)

        payload: dict[str, Any] = {
            "success":         not has_error,
            "status":          overall_status,
            "version":         API_VERSION,
            "timestamp":       datetime.now(tz=timezone.utc).isoformat(),
            "uptime_seconds":  uptime_seconds,
            "check_time_ms":   elapsed_ms,
            "checks":          checks,
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

        from django.http import JsonResponse
        return JsonResponse(payload, status=http_status)
