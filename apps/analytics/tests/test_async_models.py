"""
Async model method tests for apps.analytics.models.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.analytics.models import (
    Alert,
    AlertRule,
    BusinessMetric,
    Metric,
    PerformanceMetric,
    UserActivity,
)

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_metric_aget_by_type_and_latest():
    """Metric async methods should filter by type and return latest records."""
    await Metric.objects.acreate(name="counter_a", metric_type="counter", value=1.0)
    await Metric.objects.acreate(name="gauge_a", metric_type="gauge", value=2.0)

    counters = await Metric.aget_by_type("counter")
    assert len(counters) == 1
    assert counters[0].metric_type == "counter"

    latest = await Metric.aget_latest(limit=2)
    assert len(latest) == 2


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_activity_aget_analytics_summary():
    """UserActivity async summary should aggregate activity counts."""
    user = User.objects.create_user(email="async@test.com", password="TestPass123!")
    await UserActivity.objects.acreate(user=user, action="login", resource="auth")
    await UserActivity.objects.acreate(user=user, action="view", resource="product")

    summary = await UserActivity.aget_analytics_summary(
        date_from=timezone.now().replace(hour=0, minute=0, second=0),
        date_to=timezone.now(),
    )

    assert summary["total_activities"] == 2
    assert summary["unique_users"] == 1
    assert summary["unique_actions"] == 2


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_performance_metric_aget_slow_queries_and_summary():
    """PerformanceMetric async methods should identify slow queries and summarize."""
    await PerformanceMetric.objects.acreate(
        endpoint="/slow/", method="GET", response_time_ms=1200, status_code=500
    )
    await PerformanceMetric.objects.acreate(
        endpoint="/fast/", method="GET", response_time_ms=50, status_code=200
    )

    slow = await PerformanceMetric.aget_slow_queries(threshold_ms=1000)
    assert len(slow) == 1
    assert slow[0].endpoint == "/slow/"

    summary = await PerformanceMetric.aget_performance_summary(
        date_from=timezone.now().replace(hour=0, minute=0, second=0),
        date_to=timezone.now(),
    )
    assert summary["total_requests"] == 2
    assert summary["error_rate"] == 1


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_business_metric_aget_trend():
    """BusinessMetric async trend should return the latest N records."""
    now = timezone.now()
    from datetime import timedelta
    for i in range(3):
        await BusinessMetric.objects.acreate(
            metric_name="total_gmv",
            value=float(i + 1),
            period_start=now - timedelta(hours=3 - i),
            period_end=now - timedelta(hours=2 - i),
        )

    trend = await BusinessMetric.aget_trend("total_gmv", periods=3)
    assert len(trend) == 3


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_alert_rule_aget_by_severity():
    """AlertRule async severity selector should return active rules by severity."""
    await AlertRule.objects.acreate(
        name="rule_high", metric_name="m1", operator="gt", threshold=1.0, severity="high"
    )
    await AlertRule.objects.acreate(
        name="rule_low", metric_name="m2", operator="gt", threshold=1.0, severity="low"
    )

    high_rules = await AlertRule.aget_by_severity("high")
    assert len(high_rules) == 1
    assert high_rules[0].name == "rule_high"


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_alert_aget_by_rule_and_aresolve():
    """Alert async methods should filter by rule and resolve alerts."""
    rule = await AlertRule.objects.acreate(
        name="rule", metric_name="m", operator="gt", threshold=1.0
    )
    alert = await Alert.objects.acreate(
        rule=rule, status="firing", metric_value=2.0, message="firing"
    )

    firing = await Alert.aget_by_rule(rule_id=rule.id)
    assert len(firing) == 1

    await alert.aresolve(resolution_notes="resolved via test")
    assert alert.status == "resolved"
    assert alert.resolved_at is not None
