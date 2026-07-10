"""
Ninja endpoint tests for migrated analytics endpoints.

Verifies that platform analytics report is served from apps/analytics and that
legacy AI-router paths are no longer registered.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import AsyncClient


@pytest.fixture
def async_client():
    """Return Django async test client."""
    return AsyncClient()


@pytest.fixture
def staff_token(staff_user):
    """Return a JWT access token for the staff user."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(staff_user)
    return str(refresh.access_token)


@pytest.fixture
def user_token(regular_user):
    """Return a JWT access token for the regular user."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(regular_user)
    return str(refresh.access_token)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_get_platform_analytics_returns_cached_report(
    async_client, staff_token, mock_report
):
    """GET /api/v1/ninja/analytics/platform/ returns a cached report when present."""
    cache_key = "analytics:report:platform:platform:7d"
    cache.set(cache_key, json.dumps(mock_report), timeout=60)

    response = await async_client.get(
        "/api/v1/ninja/analytics/platform/?days=7",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "platform"
    assert data["days"] == 7
    assert data["order_metrics"]["total_orders"] == 10

    cache.delete(cache_key)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_get_platform_analytics_triggers_generation_when_missing(
    async_client, staff_token
):
    """GET /api/v1/ninja/analytics/platform/ triggers background generation when cache miss."""
    cache.delete("analytics:report:platform:platform:7d")

    with patch("apps.analytics.tasks.analytics_tasks.run_platform_analytics") as mock_task:
        mock_task.delay.return_value = None
        response = await async_client.get(
            "/api/v1/ninja/analytics/platform/?days=7",
            headers={"Authorization": f"Bearer {staff_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "platform"
    assert data["llm_insights"] == "Report generation in progress..."
    mock_task.delay.assert_called_once_with(days=7)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_get_platform_analytics_forbidden_for_regular_user(
    async_client, user_token
):
    """Non-staff users should receive 403 from the platform analytics endpoint."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/platform/?days=7",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_legacy_ai_analytics_platform_path_removed(
    async_client, staff_token
):
    """Legacy GET /api/v1/ninja/ai/analytics/platform/ should no longer be registered."""
    response = await async_client.get(
        "/api/v1/ninja/ai/analytics/platform/?days=7",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_ai_health_endpoint_remains(async_client):
    """GET /api/v1/ninja/ai/health/ must remain public and reachable."""
    response = await async_client.get("/api/v1/ninja/ai/health/")

    # The endpoint is public; we only assert it is still registered.
    assert response.status_code in (200, 503, 502)
