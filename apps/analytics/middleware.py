# apps/analytics/middleware.py
"""
Analytics middleware for request/response performance tracking and real-time
event publishing.

Can be enabled by adding `apps.analytics.middleware.AnalyticsMiddleware` to
`MIDDLEWARE` after authentication middleware. It is safe to install in both sync
and ASGI deployments: sync views will run the sync path, async views will run
the async path.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from django.http import HttpRequest, HttpResponse

from apps.analytics.services.metrics_service import get_metrics_service
from apps.analytics.services.realtime_service import publish_analytics_event

logger = logging.getLogger(__name__)


class AnalyticsMiddleware:
    """
    Records request latency, status code, and publishes a lightweight real-time
    analytics event for every request.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Optional[Callable] = None):
        self.get_response = get_response
        self.is_async = False
        if get_response is not None:
            self.is_async = getattr(get_response, "is_async", False)
        self.metrics = get_metrics_service()

    def __call__(self, request: HttpRequest):
        if self.is_async:
            return self._aprocess_request(request)
        return self._process_request(request)

    def _process_request(self, request: HttpRequest) -> HttpResponse:
        start = time.perf_counter()
        response = self.get_response(request)
        self._record(request, response, time.perf_counter() - start)
        return response

    async def _aprocess_request(self, request: HttpRequest):
        start = time.perf_counter()
        response = await self.get_response(request)
        self._record(request, response, time.perf_counter() - start)
        return response

    def _record(self, request: HttpRequest, response: HttpResponse, duration: float):
        try:
            status_code = getattr(response, "status_code", 0)
            endpoint = request.path
            method = request.method or "UNKNOWN"
            duration_ms = int(duration * 1000)

            self.metrics.record_query(
                query_type=f"{method}:{endpoint}",
                duration_seconds=duration,
            )

            user = getattr(request, "user", None)
            user_id = str(user.id) if user and user.is_authenticated else None

            if status_code >= 500:
                self.metrics.record_error(source="http_5xx")

            publish_analytics_event(
                event_type="api_call",
                user_id=user_id,
                endpoint=endpoint,
                response_time_ms=duration_ms,
                status_code=status_code,
                metadata={"method": method},
            )
        except Exception as exc:
            logger.warning("[AnalyticsMiddleware] failed to record request: %s", exc)
