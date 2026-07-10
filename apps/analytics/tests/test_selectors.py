"""
Selector tests for apps.analytics.selectors.analytics_selectors.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.analytics.models import Alert, AlertRule, BusinessMetric, Metric, PerformanceMetric, UserActivity
from apps.analytics.selectors.analytics_selectors import (
    aget_alert_dashboard_parallel,
    aget_analytics_dashboard_parallel,
    aget_metrics,
    aget_performance_dashboard_parallel,
    get_alerts,
    get_metrics,
    get_user_activity,
)

User = get_user_model()


@pytest.mark.django_db
def test_sync_selectors():
    """Sync selectors should return the requested analytics records."""
    metric = Metric.objects.create(name="m1", metric_type="gauge", value=1.0)
    metrics = get_metrics(name="m1")
    assert len(metrics) == 1
    assert metrics[0].id == metric.id

    user = User.objects.create(email="sync@test.com")
    UserActivity.objects.create(user=user, action="login")
    activities = get_user_activity(user_id=user.id)
    assert len(activities) == 1

    rule = AlertRule.objects.create(name="rule", metric_name="m", operator="gt", threshold=1.0)
    Alert.objects.create(rule=rule, status="firing", metric_value=2.0, message="alert")
    alerts = get_alerts(status="firing")
    assert len(alerts) == 1


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_aget_metrics():
    """Async metric selector should filter by name and type."""
    await Metric.objects.acreate(name="m2", metric_type="counter", value=1.0)
    by_name = await aget_metrics(name="m2")
    assert len(by_name) == 1

    by_type = await aget_metrics(metric_type="counter")
    assert len(by_type) == 1


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_aget_analytics_dashboard_parallel():
    """Parallel dashboard selector should return combined data."""
    user = await User.objects.acreate(email="dash@test.com")
    await UserActivity.objects.acreate(user=user, action="login")
    await PerformanceMetric.objects.acreate(
        endpoint="/", method="GET", response_time_ms=100, status_code=200
    )
    await BusinessMetric.objects.acreate(
        metric_name="gmv", value=1.0, period_start=timezone.now(), period_end=timezone.now()
    )
    rule = await AlertRule.objects.acreate(name="r", metric_name="m", operator="gt", threshold=1.0)
    await Alert.objects.acreate(rule=rule, status="firing", metric_value=2.0, message="x")

    data = await aget_analytics_dashboard_parallel(user_id=str(user.id))

    assert data["performance_count"] >= 1
    assert data["business_count"] >= 1
    assert data["alert_count"] >= 1
    assert data["activity_count"] >= 1


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_aget_performance_dashboard_parallel():
    """Performance dashboard parallel selector should summarize performance metrics."""
    await PerformanceMetric.objects.acreate(
        endpoint="/slow/", method="GET", response_time_ms=1200, status_code=500
    )

    data = await aget_performance_dashboard_parallel(hours=24)
    assert data["slow_query_count"] >= 1
    assert "summary" in data


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_aget_alert_dashboard_parallel():
    """Alert dashboard parallel selector should return firing and resolved alerts."""
    rule = await AlertRule.objects.acreate(name="r", metric_name="m", operator="gt", threshold=1.0)
    await Alert.objects.acreate(rule=rule, status="firing", metric_value=2.0, message="x")
    await Alert.objects.acreate(rule=rule, status="resolved", metric_value=2.0, message="x")

    data = await aget_alert_dashboard_parallel()
    assert data["firing_count"] == 1
    assert data["resolved_count"] == 1
    assert data["active_rule_count"] >= 1
