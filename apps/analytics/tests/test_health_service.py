"""
Tests for apps.analytics.services.health_service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.analytics.services.health_service import AnalyticsHealthService


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_aget_health_returns_healthy():
    """Health service should return healthy when all probes succeed."""
    with patch.object(
        AnalyticsHealthService, "_acheck_database", return_value=MagicMock(name="database", status="healthy", response_time_ms=1.0, message="ok", metadata={})
    ), patch.object(
        AnalyticsHealthService, "_acheck_cache", return_value=MagicMock(name="cache", status="healthy", response_time_ms=1.0, message="ok", metadata={})
    ), patch.object(
        AnalyticsHealthService, "_acheck_celery", return_value=MagicMock(name="celery", status="healthy", response_time_ms=1.0, message="ok", metadata={})
    ):
        result = await AnalyticsHealthService.aget_health()

    assert result["service"] == "analytics"
    assert result["status"] == "healthy"
    assert "checks" in result
    assert len(result["checks"]) == 3


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_aget_health_unhealthy_when_database_fails():
    """Health service should report unhealthy when database check fails."""
    with patch.object(
        AnalyticsHealthService, "_acheck_database", return_value=MagicMock(name="database", status="unhealthy", response_time_ms=0.0, message="fail", metadata={})
    ), patch.object(
        AnalyticsHealthService, "_acheck_cache", return_value=MagicMock(name="cache", status="healthy", response_time_ms=1.0, message="ok", metadata={})
    ), patch.object(
        AnalyticsHealthService, "_acheck_celery", return_value=MagicMock(name="celery", status="healthy", response_time_ms=1.0, message="ok", metadata={})
    ):
        result = await AnalyticsHealthService.aget_health()

    assert result["status"] == "unhealthy"
