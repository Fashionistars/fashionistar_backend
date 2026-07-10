"""
Unit tests for apps.analytics.tasks.analytics_tasks.

Migrated from apps.ai.tasks.analytics_tasks as part of analytics modernization.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.analytics.tasks.analytics_tasks import (
    generate_daily_report,
    run_platform_analytics,
    run_product_performance_analysis,
    run_user_behavior_analysis,
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
def test_run_user_behavior_analysis_uses_analytics_cache_prefix():
    """User behaviour task should write to analytics:report:user:* cache namespace."""
    user_id = 42
    cache.delete(f"analytics:report:user:{user_id}")

    with patch("apps.ai.database.access_layer.FashionistarDatabaseLayer") as mock_db:
        instance = MagicMock()
        instance.get_user_full_context.return_value = {"recent_categories": ["shirts"]}
        instance.get_user_order_history.return_value = [{"id": 1}]
        instance.get_user_measurements.return_value = [{"is_default": True}]
        mock_db.return_value = instance

        result = run_user_behavior_analysis(user_id=user_id, days=30)

    assert result["user_id"] == user_id
    assert "shirts" in result["purchase_categories"]
    assert cache.get(f"analytics:report:user:{user_id}") is not None


@pytest.mark.django_db
def test_run_product_performance_analysis_uses_analytics_cache_prefix():
    """Product performance task should write to analytics:report:product:* cache namespace."""
    product_id = 7
    cache.delete(f"analytics:report:product:{product_id}")

    with patch("apps.ai.database.access_layer.FashionistarDatabaseLayer") as mock_db:
        instance = MagicMock()
        instance.get_product_full.return_value = {
            "name": "Test Product",
            "category": "Shirts",
            "view_count": 100,
            "sales_count": 5,
        }
        mock_db.return_value = instance

        result = run_product_performance_analysis(product_id=product_id, days=30)

    assert result["product_id"] == product_id
    assert result["name"] == "Test Product"
    assert cache.get(f"analytics:report:product:{product_id}") is not None


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
