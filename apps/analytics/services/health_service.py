# apps/analytics/services/health_service.py
"""
Health check service for the analytics domain.

Performs lightweight async checks against the database, Redis cache, and Celery
worker availability. Designed to be consumed by a Ninja endpoint and by
platform-level observability probes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import connections, DatabaseError

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Import Celery app lazily to avoid startup-time import side effects."""
    from celery import current_app
    return current_app


@dataclass
class HealthCheckResult:
    """Result of an individual health probe."""
    name: str
    status: str  # healthy | degraded | unhealthy
    response_time_ms: float
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class AnalyticsHealthService:
    """Analytics health check aggregator."""

    @classmethod
    async def aget_health(cls) -> Dict[str, Any]:
        """
        Run all analytics health probes concurrently and return an aggregated report.
        """
        start = time.perf_counter()

        checks = await cls._arun_checks(
            [
                cls._acheck_database,
                cls._acheck_cache,
                cls._acheck_celery,
            ]
        )

        total_ms = (time.perf_counter() - start) * 1000
        overall = "healthy"
        for check in checks:
            if check.status == "unhealthy":
                overall = "unhealthy"
                break
            elif check.status == "degraded" and overall == "healthy":
                overall = "degraded"

        return {
            "service": "analytics",
            "status": overall,
            "response_time_ms": round(total_ms, 2),
            "checks": [cls._serialize_check(c) for c in checks],
        }

    @classmethod
    async def _arun_checks(cls, check_funcs) -> List[HealthCheckResult]:
        """Run a list of async probe coroutines."""
        import asyncio

        results = await asyncio.gather(
            *[f() for f in check_funcs],
            return_exceptions=True,
        )

        checks = []
        for func, result in zip(check_funcs, results):
            if isinstance(result, Exception):
                name = func.__name__.replace("_acheck_", "")
                checks.append(
                    HealthCheckResult(
                        name=name,
                        status="unhealthy",
                        response_time_ms=0.0,
                        message=str(result),
                    )
                )
            else:
                checks.append(result)
        return checks

    @classmethod
    async def _acheck_database(cls) -> HealthCheckResult:
        """Verify that the default database connection is usable."""
        start = time.perf_counter()
        try:
            await sync_to_async(connections["default"].cursor)()
            duration_ms = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                name="database",
                status="healthy",
                response_time_ms=round(duration_ms, 2),
                message="Database connection OK",
            )
        except DatabaseError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning("[AnalyticsHealthService] database check failed: %s", exc)
            return HealthCheckResult(
                name="database",
                status="unhealthy",
                response_time_ms=round(duration_ms, 2),
                message=f"Database error: {exc}",
            )

    @classmethod
    async def _acheck_cache(cls) -> HealthCheckResult:
        """Verify that the configured Django cache backend is reachable."""
        start = time.perf_counter()
        try:
            await sync_to_async(cache.set)("analytics:health:ping", "pong", timeout=5)
            value = await sync_to_async(cache.get)("analytics:health:ping")
            duration_ms = (time.perf_counter() - start) * 1000
            status = "healthy" if value == "pong" else "degraded"
            return HealthCheckResult(
                name="cache",
                status=status,
                response_time_ms=round(duration_ms, 2),
                message="Cache ping OK" if status == "healthy" else "Cache returned unexpected value",
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning("[AnalyticsHealthService] cache check failed: %s", exc)
            return HealthCheckResult(
                name="cache",
                status="unhealthy",
                response_time_ms=round(duration_ms, 2),
                message=f"Cache error: {exc}",
            )

    @classmethod
    async def _acheck_celery(cls) -> HealthCheckResult:
        """Verify that at least one Celery worker is connected."""
        start = time.perf_counter()
        try:
            app = _get_celery_app()
            inspect = app.control.inspect(timeout=2.0)
            active_workers = await sync_to_async(inspect.active, thread_sensitive=False)()
            duration_ms = (time.perf_counter() - start) * 1000

            if active_workers:
                worker_ids = list(active_workers.keys())
                return HealthCheckResult(
                    name="celery",
                    status="healthy",
                    response_time_ms=round(duration_ms, 2),
                    message=f"{len(worker_ids)} Celery worker(s) connected",
                    metadata={"workers": worker_ids},
                )
            return HealthCheckResult(
                name="celery",
                status="degraded",
                response_time_ms=round(duration_ms, 2),
                message="No active Celery workers detected",
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning("[AnalyticsHealthService] celery check failed: %s", exc)
            return HealthCheckResult(
                name="celery",
                status="degraded",
                response_time_ms=round(duration_ms, 2),
                message=f"Celery inspect error: {exc}",
            )

    @staticmethod
    def _serialize_check(check: HealthCheckResult) -> Dict[str, Any]:
        return {
            "name": check.name,
            "status": check.status,
            "response_time_ms": check.response_time_ms,
            "message": check.message,
            "metadata": check.metadata,
        }


async def aget_analytics_health() -> Dict[str, Any]:
    """Convenience async entry point for the analytics health report."""
    return await AnalyticsHealthService.aget_health()
