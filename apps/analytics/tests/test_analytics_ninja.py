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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_platform_analytics_returns_cached_report(
    async_client, staff_token, mock_report
):
    """GET /api/v1/ninja/analytics/platform/overview/ returns a cached report when present."""
    cache_key = "analytics:report:platform:platform:7d"
    cache.set(cache_key, json.dumps(mock_report), timeout=60)

    response = await async_client.get(
        "/api/v1/ninja/analytics/platform/overview/?days=7",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "platform"
    assert data["days"] == 7
    assert data["order_metrics"]["total_orders"] == 10

    cache.delete(cache_key)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_platform_analytics_triggers_generation_when_missing(
    async_client, staff_token
):
    """GET /api/v1/ninja/analytics/platform/overview/ triggers background generation when cache miss."""
    cache.delete("analytics:report:platform:platform:7d")

    with patch("apps.analytics.tasks.analytics_tasks.run_platform_analytics") as mock_task:
        mock_task.delay.return_value = None
        response = await async_client.get(
            "/api/v1/ninja/analytics/platform/overview/?days=7",
            headers={"Authorization": f"Bearer {staff_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "platform"
    assert data["llm_insights"] == "Report generation in progress..."
    mock_task.delay.assert_called_once_with(days=7)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_platform_analytics_forbidden_for_regular_user(
    async_client, user_token
):
    """Non-staff users should receive 403 from the platform analytics endpoint."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/platform/overview/?days=7",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_vendor_analytics_triggers_generation(
    async_client, staff_token
):
    """GET /api/v1/ninja/analytics/vendors/{id}/overview/ triggers vendor report generation."""
    cache.delete("analytics:report:vendor:3:7d")

    with patch("apps.analytics.tasks.analytics_tasks.run_platform_analytics") as mock_task:
        mock_task.delay.return_value = None
        response = await async_client.get(
            "/api/v1/ninja/analytics/vendors/3/overview/?days=7",
            headers={"Authorization": f"Bearer {staff_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "vendor"
    assert data["days"] == 7
    mock_task.delay.assert_called_once_with(days=7, scope="vendor", scope_id=3)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_order_analytics_returns_stub(async_client, staff_token):
    """GET /api/v1/ninja/analytics/orders/ returns an order analytics stub."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/orders/?days=30",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "orders"
    assert data["days"] == 30


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_product_analytics_returns_stub(async_client, staff_token):
    """GET /api/v1/ninja/analytics/products/ returns a product analytics stub."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/products/?days=30",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "products"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_user_analytics_returns_stub(async_client, staff_token):
    """GET /api/v1/ninja/analytics/users/ returns a user analytics stub."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/users/?days=30",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "users"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_realtime_analytics_returns_snapshot_or_stub(
    async_client, staff_token
):
    """GET /api/v1/ninja/analytics/realtime/ returns realtime snapshot or stub."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/realtime/",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_ai_health_endpoint_remains(async_client):
    """GET /api/v1/ninja/ai/health/ must remain public and reachable."""
    response = await async_client.get("/api/v1/ninja/ai/health/")

    # The endpoint is public; we only assert it is still registered.
    assert response.status_code in (200, 503, 502)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_get_analytics_health_is_public(async_client):
    """GET /api/v1/ninja/analytics/health/ should be public and return status."""
    response = await async_client.get("/api/v1/ninja/analytics/health/")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "analytics"
    assert "status" in data
    assert "checks" in data


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_get_analytics_metrics_export_is_public(async_client):
    """GET /api/v1/ninja/analytics/metrics/export/ should be public and return Prometheus text."""
    response = await async_client.get("/api/v1/ninja/analytics/metrics/export/")

    assert response.status_code == 200
    assert response["content-type"].startswith("text/plain")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_post_metric_creates_record(async_client, staff_token):
    """POST /api/v1/ninja/analytics/metrics/ should create a metric."""
    payload = {
        "name": "revenue",
        "metric_type": "gauge",
        "value": 1234.56,
        "tags": {"currency": "USD"},
    }
    response = await async_client.post(
        "/api/v1/ninja/analytics/metrics/",
        data=payload,
        content_type="application/json",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "revenue"
    assert data["value"] == pytest.approx(1234.56)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_post_business_metric_creates_record(async_client, staff_token):
    """POST /api/v1/ninja/analytics/business-metrics/ should create a business metric."""
    from django.utils import timezone

    period = timezone.now()
    payload = {
        "metric_name": "monthly_orders",
        "value": 99.0,
        "period_start": period.isoformat(),
        "period_end": period.isoformat(),
    }
    response = await async_client.post(
        "/api/v1/ninja/analytics/business-metrics/",
        data=payload,
        content_type="application/json",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metric_name"] == "monthly_orders"
    assert data["value"] == pytest.approx(99.0)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_post_resolve_alert_updates_status(async_client, staff_token, alert_firing):
    """POST /api/v1/ninja/analytics/alerts/{id}/resolve/ should resolve an alert."""
    response = await async_client.post(
        f"/api/v1/ninja/analytics/alerts/{alert_firing.id}/resolve/",
        data={"resolution_notes": "Investigated and fixed"},
        content_type="application/json",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert "resolved_at" in data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_user_activity_returns_list(async_client, staff_token):
    """GET /api/v1/ninja/analytics/user-activity/ should return user activity."""
    response = await async_client.get(
        "/api/v1/ninja/analytics/user-activity/?limit=10",
        headers={"Authorization": f"Bearer {staff_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)
