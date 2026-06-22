# apps/common/telemetry_api.py
"""
FASHIONISTAR — Core Web Vitals Telemetry Django Ninja Router.

Receives real-world performance metrics (LCP, INP, CLS, FID) forwarded from
the Next.js storefront Edge Route Handler (`/api/telemetry/vitals`).

Architecture:
  - Authenticated exclusively by the `InternalServiceOnly` class which
    verifies the `X-Internal-Token` header against the configured secret.
  - Metrics below SLA thresholds → Redis counter increment (zero DB write).
  - Metrics breaching SLA thresholds → Async PostgreSQL write to
    `SlowPerformanceAuditLog` + structured WARNING log.

SLA Thresholds (Google CWV 2026 guidelines):
  LCP  ≤ 2500ms   (Largest Contentful Paint)
  FID  ≤ 100ms    (First Input Delay — legacy)
  CLS  ≤ 0.10     (Cumulative Layout Shift)
  INP  ≤ 200ms    (Interaction to Next Paint)
  TTFB ≤ 800ms    (Time to First Byte)

Mount point: /api/v1/ninja/common/telemetry/
Full path  : POST /api/v1/ninja/common/telemetry/vitals/
"""

from __future__ import annotations

import logging
import os

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema
from ninja.security import APIKeyHeader

logger = logging.getLogger("fashionistar.telemetry")

# ── Internal Service Token Authentication ────────────────────────────────────


class _InternalTokenAuth(APIKeyHeader):
    """
    Ninja-compatible authentication class for internal service-to-service calls.

    Validates the `X-Internal-Token` request header against the value of the
    `INTERNAL_SERVICE_TOKEN` environment variable. Only Next.js edge routes
    or other trusted internal services should possess this token.

    If the token is absent or invalid, Ninja returns HTTP 401 Unauthorized
    automatically before the view handler is invoked.
    """

    param_name = "X-Internal-Token"

    def authenticate(self, request: HttpRequest, key: str | None):  # type: ignore[override]
        expected = os.environ.get(
            "INTERNAL_SERVICE_TOKEN",
            "telemetry-secret-key-2026",
        )
        if key and key == expected:
            # Return a truthy sentinel so Ninja marks the request as authenticated.
            return "internal-service"
        logger.warning(
            "[InternalServiceOnly] Unauthorized telemetry request from %s",
            request.META.get("REMOTE_ADDR", "unknown"),
        )
        return None


#: Singleton instance — imported by view decorators.
InternalServiceOnly = _InternalTokenAuth()


# ── Payload Schema ────────────────────────────────────────────────────────────


class WebVitalSchema(Schema):
    """Validated payload shape from the Next.js edge telemetry route."""

    metric_id: str
    metric_name: str
    metric_label: str
    metric_value: float
    page_path: str
    user_agent: str
    ip_address: str


# ── SLA Thresholds ────────────────────────────────────────────────────────────

_SLA: dict[str, float] = {
    "LCP": 2500.0,   # ms
    "FID": 100.0,    # ms
    "CLS": 0.10,     # unitless
    "INP": 200.0,    # ms
    "TTFB": 800.0,   # ms
}


# ── Router ────────────────────────────────────────────────────────────────────

telemetry_router = Router(tags=["telemetry"])


@telemetry_router.post("/vitals/", auth=InternalServiceOnly)
async def record_performance_vitals(request: HttpRequest, payload: WebVitalSchema):
    """
    Asynchronously processes Core Web Vitals payload from Next.js edge.

    Routing logic:
      - metric ≤ SLA → Redis counter increment (no DB write, high throughput)
      - metric > SLA → PostgreSQL append-only log + WARNING log entry

    Returns:
        ``{"status": "recorded", "slow_alert": bool}``
    """
    metric_name = payload.metric_name
    metric_value = payload.metric_value

    # ── SLA classification ────────────────────────────────────────────────
    threshold = _SLA.get(metric_name)
    is_slow = bool(threshold is not None and metric_value > threshold)

    if is_slow:
        # ── Slow path: persist SLA breach to PostgreSQL ───────────────────
        try:
            from apps.common.models import SlowPerformanceAuditLog

            await SlowPerformanceAuditLog.objects.acreate(
                metric_id=payload.metric_id,
                metric_name=metric_name,
                metric_value=metric_value,
                page_path=payload.page_path,
                user_agent=payload.user_agent,
                ip_address=payload.ip_address or None,
                logged_at=timezone.now(),
            )
            logger.warning(
                "[SLA Breach] metric=%s value=%.2f threshold=%.2f path=%s",
                metric_name,
                metric_value,
                threshold,
                payload.page_path,
            )
        except Exception as exc:  # noqa: BLE001
            # Never raise — telemetry must never break the storefront.
            logger.error("[Telemetry DB Write Failed] %s", exc)
    else:
        # ── Fast path: increment Redis OK counter (zero DB writes) ────────
        try:
            from django.core.cache import cache

            cache_key = f"telemetry:ok_count:{metric_name}"
            try:
                cache.incr(cache_key)
            except ValueError:
                # Key does not exist yet — initialize it.
                cache.set(cache_key, 1, timeout=86_400)  # 24-hour rolling window
        except Exception as exc:  # noqa: BLE001
            logger.debug("[Telemetry Redis Write Failed] %s", exc)

    return {"status": "recorded", "slow_alert": is_slow}
