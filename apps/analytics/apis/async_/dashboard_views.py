"""
apps/analytics/apis/async_/dashboard_views.py
==============================================
Admin-only dashboard endpoints for analytics system health and observability.

All endpoints require staff/admin access and are rate-limited.
Data is cached for 60 seconds via DashboardService.
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError

from apps.analytics.services.dashboard_service import DashboardService
from apps.common.throttling import (
    UserBurstThrottle,
    UserSustainedThrottle,
    get_ninja_throttle,
)

router = Router(tags=["Analytics Dashboard"])


def _check_admin(request: HttpRequest) -> None:
    """Verify the request user has staff or admin access."""
    user = request.auth
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        raise HttpError(403, "Staff or admin access required.")


@router.get(
    "/overview/",
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_system_overview(request: HttpRequest) -> dict:
    """
    Get analytics system overview (admin only).
    Endpoint: GET /api/v1/ninja/analytics/dashboard/overview/
    """
    _check_admin(request)
    return await DashboardService.aget_system_overview()


@router.get(
    "/ingestion-rate/",
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_ingestion_rate(
    request: HttpRequest,
    hours: int = 24,
) -> dict:
    """
    Get ingestion rate data points (admin only).
    Endpoint: GET /api/v1/ninja/analytics/dashboard/ingestion-rate/?hours=24
    """
    _check_admin(request)
    if hours < 1 or hours > 168:
        raise HttpError(400, "hours must be between 1 and 168 (7 days).")
    return await DashboardService.aget_ingestion_rate(hours=hours)


@router.get(
    "/latency-distribution/",
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_latency_distribution(
    request: HttpRequest,
    hours: int = 24,
) -> dict:
    """
    Get query latency distribution (admin only).
    Endpoint: GET /api/v1/ninja/analytics/dashboard/latency-distribution/?hours=24
    """
    _check_admin(request)
    if hours < 1 or hours > 168:
        raise HttpError(400, "hours must be between 1 and 168 (7 days).")
    return await DashboardService.aget_query_latency_distribution(hours=hours)


@router.get(
    "/error-rate/",
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_error_rate(
    request: HttpRequest,
    hours: int = 24,
) -> dict:
    """
    Get error rate by endpoint (admin only).
    Endpoint: GET /api/v1/ninja/analytics/dashboard/error-rate/?hours=24
    """
    _check_admin(request)
    if hours < 1 or hours > 168:
        raise HttpError(400, "hours must be between 1 and 168 (7 days).")
    return await DashboardService.aget_error_rate_by_endpoint(hours=hours)


@router.get(
    "/cache-stats/",
    throttle=get_ninja_throttle(UserBurstThrottle, UserSustainedThrottle),
)
async def get_cache_stats(request: HttpRequest) -> dict:
    """
    Get cache hit/miss statistics (admin only).
    Endpoint: GET /api/v1/ninja/analytics/dashboard/cache-stats/
    """
    _check_admin(request)
    return await DashboardService.aget_cache_stats()
