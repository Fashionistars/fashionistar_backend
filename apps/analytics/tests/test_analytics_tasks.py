"""
Unit tests for apps.analytics.tasks.analytics_tasks.

Migrated from apps.ai.tasks.analytics_tasks as part of analytics modernization.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.analytics.tasks.analytics_tasks import (
    generate_daily_report,
    run_platform_analytics,
    run_product_performance_analysis,
    run_realtime_analytics,
    run_user_behavior_analysis,
    run_vendor_analytics,
)
from apps.analytics.tasks.aggregation_tasks import (
    rollup_1d,
    rollup_1h,
    rollup_1m,
    rollup_5m,
)


@pytest.mark.django_db
def test_run_platform_analytics_uses_migrated_workflow():
    """The Celery task should invoke the migrated AnalyticsWorkflow."""
    mock_workflow = MagicMock()
    mock_workflow.execute.return_value = {"anomalies": [], "llm_insights": ""}

    with patch("apps.analytics.tasks.analytics_tasks.AnalyticsWorkflow", return_value=mock_workflow):
        result = run_platform_analytics(days=7, scope="platform")

    assert result["anomalies"] == []
    mock_workflow.execute.assert_called_once_with(
        {"days": 7, "scope": "platform", "scope_id": None}
    )


@pytest.mark.django_db
def test_run_user_behavior_analysis_uses_migrated_workflow():
    """User behaviour task should invoke the migrated UserBehaviorWorkflow."""
    user_id = 42
    mock_workflow = MagicMock()
    mock_workflow.execute.return_value = {
        "user_id": user_id,
        "purchase_categories": ["shirts"],
    }

    with patch(
        "apps.analytics.tasks.analytics_tasks.UserBehaviorWorkflow",
        return_value=mock_workflow,
    ):
        result = run_user_behavior_analysis(user_id=user_id, days=30)

    assert result["user_id"] == user_id
    assert "shirts" in result["purchase_categories"]
    mock_workflow.execute.assert_called_once_with(
        {"user_id": user_id, "days": 30}
    )


@pytest.mark.django_db
def test_run_product_performance_analysis_uses_migrated_workflow():
    """Product performance task should invoke the migrated ProductPerformanceWorkflow."""
    product_id = 7
    mock_workflow = MagicMock()
    mock_workflow.execute.return_value = {
        "product_id": product_id,
        "name": "Test Product",
    }

    with patch(
        "apps.analytics.tasks.analytics_tasks.ProductPerformanceWorkflow",
        return_value=mock_workflow,
    ):
        result = run_product_performance_analysis(product_id=product_id, days=30)

    assert result["product_id"] == product_id
    assert result["name"] == "Test Product"
    mock_workflow.execute.assert_called_once_with(
        {"product_id": product_id, "days": 30}
    )


@pytest.mark.django_db
def test_generate_daily_report_triggers_platform_analytics():
    """Daily report task should dispatch run_platform_analytics for 1, 7, and 30 days."""
    with patch(
        "apps.analytics.tasks.analytics_tasks.run_platform_analytics"
    ) as mock_task:
        mock_task.apply.return_value = MagicMock()
        generate_daily_report()

    assert mock_task.apply.call_count == 3
    call_kwargs = [call.kwargs for call in mock_task.apply.call_args_list]
    requested_days = {kw["kwargs"]["days"] for kw in call_kwargs}
    assert requested_days == {1, 7, 30}


@pytest.mark.django_db
def test_run_vendor_analytics_uses_migrated_workflow():
    """The vendor analytics task should invoke the migrated VendorPerformanceWorkflow."""
    vendor_id = 3
    mock_workflow = MagicMock()
    mock_workflow.execute.return_value = {"vendor_id": vendor_id, "gmv": 1000}

    with patch(
        "apps.analytics.tasks.analytics_tasks.VendorPerformanceWorkflow",
        return_value=mock_workflow,
    ):
        result = run_vendor_analytics(vendor_id=vendor_id, days=30)

    assert result["vendor_id"] == vendor_id
    mock_workflow.execute.assert_called_once_with(
        {"vendor_id": vendor_id, "days": 30}
    )


@pytest.mark.django_db
def test_run_realtime_analytics_caches_snapshot():
    """The real-time analytics task should cache a snapshot."""
    from django.core.cache import cache

    cache.delete("analytics:realtime:snapshot")

    result = run_realtime_analytics()

    assert "generated_at" in result
    assert cache.get("analytics:realtime:snapshot") is not None


@pytest.mark.django_db
def test_rollup_1m_caches_result():
    """1-minute rollup task should cache an aggregated result."""
    from django.core.cache import cache
    from django.utils import timezone

    with patch("apps.analytics.tasks.aggregation_tasks._run_async") as mock_run, patch(
        "apps.analytics.tasks.aggregation_tasks.AnalyticsAuditService.log_metric_aggregation_executed"
    ):
        mock_run.return_value = {
            "metric_count": 5,
            "request_count": 10,
            "window_start": timezone.now().isoformat(),
            "window_end": timezone.now().isoformat(),
        }
        rollup_1m()

    cache_key = f"analytics:rollup:1m:{timezone.now().strftime('%Y%m%d%H%M')}"
    cached = cache.get(cache_key)
    assert cached is not None


@pytest.mark.django_db
def test_rollup_5m_caches_result():
    """5-minute rollup task should cache an aggregated result."""
    from django.core.cache import cache
    from django.utils import timezone

    with patch("apps.analytics.tasks.aggregation_tasks._run_async") as mock_run, patch(
        "apps.analytics.tasks.aggregation_tasks.AnalyticsAuditService.log_metric_aggregation_executed"
    ):
        mock_run.return_value = {
            "metric_count": 3,
            "request_count": 7,
            "window_start": timezone.now().isoformat(),
            "window_end": timezone.now().isoformat(),
        }
        rollup_5m()

    cache_key = f"analytics:rollup:5m:{timezone.now().strftime('%Y%m%d%H%M')}"
    cached = cache.get(cache_key)
    assert cached is not None


@pytest.mark.django_db
def test_rollup_1h_caches_result():
    """1-hour rollup task should cache an aggregated result."""
    from django.core.cache import cache
    from django.utils import timezone

    with patch("apps.analytics.tasks.aggregation_tasks._run_async") as mock_run, patch(
        "apps.analytics.tasks.aggregation_tasks.AnalyticsAuditService.log_metric_aggregation_executed"
    ):
        mock_run.return_value = {
            "metric_count": 50,
            "request_count": 120,
            "window_start": timezone.now().isoformat(),
            "window_end": timezone.now().isoformat(),
        }
        rollup_1h()

    cache_key = f"analytics:rollup:1h:{timezone.now().strftime('%Y%m%d%H')}"
    cached = cache.get(cache_key)
    assert cached is not None


@pytest.mark.django_db
def test_rollup_1d_caches_result():
    """1-day rollup task should cache an aggregated result."""
    from django.core.cache import cache
    from django.utils import timezone

    with patch("apps.analytics.tasks.aggregation_tasks._run_async") as mock_run, patch(
        "apps.analytics.tasks.aggregation_tasks.AnalyticsAuditService.log_metric_aggregation_executed"
    ):
        mock_run.return_value = {
            "metric_count": 500,
            "request_count": 1000,
            "window_start": timezone.now().isoformat(),
            "window_end": timezone.now().isoformat(),
        }
        rollup_1d()

    cache_key = f"analytics:rollup:1d:{timezone.now().strftime('%Y%m%d')}"
    cached = cache.get(cache_key)
    assert cached is not None
