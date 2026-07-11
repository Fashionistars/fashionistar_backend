"""
Unit tests for apps.analytics.workflows.analytics.AnalyticsWorkflow.

Migrated from apps.ai.workflows.analytics as part of analytics modernization.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.analytics.workflows.analytics import AnalyticsWorkflow
from apps.analytics.workflows.product_performance import ProductPerformanceWorkflow
from apps.analytics.workflows.user_behavior import UserBehaviorWorkflow
from apps.analytics.workflows.vendor_performance import VendorPerformanceWorkflow


@pytest.fixture
def workflow():
    """Return a fresh AnalyticsWorkflow instance."""
    return AnalyticsWorkflow()


@pytest.mark.django_db
def test_analytics_workflow_execute_returns_report(workflow, regular_user):
    """The workflow should return a report dict containing expected keys."""
    with patch("apps.ai.workflows.base.BaseWorkflow") as mock_base:
        base_instance = MagicMock()
        base_instance.start_execution.return_value = "test-exec-id"
        base_instance.complete_execution.return_value = None
        base_instance.fail_execution.return_value = None
        mock_base.return_value = base_instance

        with patch.object(
            workflow, "_aggregate_order_metrics", side_effect=lambda s: {**s, "order_metrics": {}}
        ) as _:
            with patch.object(
                workflow, "_aggregate_product_metrics", side_effect=lambda s: {**s, "product_metrics": {}}
            ):
                with patch.object(
                    workflow, "_aggregate_user_metrics", side_effect=lambda s: {**s, "user_metrics": {}}
                ):
                    with patch.object(
                        workflow, "_aggregate_vendor_metrics", side_effect=lambda s: {**s, "vendor_metrics": {}}
                    ):
                        with patch.object(
                            workflow, "_detect_anomalies", side_effect=lambda s: {**s, "anomalies": []}
                        ):
                            with patch.object(
                                workflow, "_generate_llm_insights", side_effect=lambda s: s
                            ):
                                with patch.object(
                                    workflow, "_persist_report", side_effect=lambda s: {**s, "report": {"cache_key": "analytics:report:platform:platform:7d"}}
                                ):
                                    result = workflow.execute({"days": 7, "scope": "platform"})

    assert isinstance(result, dict)
    base_instance.start_execution.assert_called_once()
    base_instance.complete_execution.assert_called_once()


@pytest.mark.django_db
def test_persist_report_uses_analytics_cache_prefix(workflow):
    """The migrated workflow must write to the analytics:report:* cache key namespace."""
    state = {
        "days": 7,
        "scope": "platform",
        "scope_id": None,
        "order_metrics": {},
        "product_metrics": {},
        "user_metrics": {},
        "vendor_metrics": {},
        "anomalies": [],
        "llm_insights": "",
        "errors": [],
    }

    new_state = workflow._persist_report(state)
    report = new_state["report"]

    assert report["cache_key"].startswith("analytics:report:")
    assert "ai:analytics:" not in report["cache_key"]


def test_detect_anomalies_detects_gmv_drop(workflow):
    """Anomaly detection should flag a >30% GMV drop as CRITICAL."""
    state = {
        "order_metrics": {
            "total_gmv": 100.0,
            "previous_period_gmv": 200.0,
        },
        "user_metrics": {},
        "product_metrics": {},
    }

    new_state = workflow._detect_anomalies(state)

    assert len(new_state["anomalies"]) == 1
    anomaly = new_state["anomalies"][0]
    assert anomaly["type"] == "GMV_DROP"
    assert anomaly["severity"] == "CRITICAL"


def test_detect_anomalies_detects_low_stock(workflow):
    """Anomaly detection should flag low inventory when count exceeds threshold."""
    state = {
        "order_metrics": {},
        "user_metrics": {},
        "product_metrics": {
            "inventory_summary": {"low_stock_count": 8},
        },
    }

    new_state = workflow._detect_anomalies(state)

    assert any(a["type"] == "LOW_STOCK" for a in new_state["anomalies"])


def test_detect_anomalies_detects_registration_spike(workflow):
    """Anomaly detection should flag a 2x registration spike as INFO."""
    state = {
        "order_metrics": {},
        "user_metrics": {
            "new_registrations": 100,
            "prev_period_registrations": 40,
        },
        "product_metrics": {},
    }

    new_state = workflow._detect_anomalies(state)

    assert any(
        a["type"] == "REGISTRATION_SPIKE" and a["severity"] == "INFO"
        for a in new_state["anomalies"]
    )


@pytest.mark.django_db
def test_generate_llm_insights_uses_entry_points(workflow):
    """The migrated workflow must call apps.analytics.entry_points for LLM insights."""
    state = {
        "days": 7,
        "order_metrics": {"total_gmv": 1000},
        "user_metrics": {"new_registrations": 5},
        "vendor_metrics": {"total_vendors": 2},
        "product_metrics": {"trending_count": 3},
        "anomalies": [],
    }

    with patch("apps.analytics.entry_points.generate_llm_insights") as mock_generate:
        mock_generate.return_value = "Insight text"
        new_state = workflow._generate_llm_insights(state)

    assert new_state["llm_insights"] == "Insight text"
    mock_generate.assert_called_once()


@pytest.mark.django_db
def test_user_behavior_workflow_caches_report(regular_user):
    """UserBehaviorWorkflow should cache a report under analytics:report:user:{user_id}."""
    cache.delete(f"analytics:report:user:{regular_user.id}")

    with patch("apps.ai.workflows.base.BaseWorkflow") as mock_base:
        base_instance = MagicMock()
        base_instance.start_execution.return_value = "test-exec-id"
        base_instance.complete_execution.return_value = None
        mock_base.return_value = base_instance

        with patch(
            "apps.ai.database.access_layer.FashionistarDatabaseLayer"
        ) as mock_db:
            instance = MagicMock()
            instance.get_user_full_context.return_value = {"recent_categories": ["shirts"]}
            instance.get_user_order_history.return_value = [{"id": 1}]
            instance.get_user_measurements.return_value = [{"is_default": True}]
            mock_db.return_value = instance

            workflow = UserBehaviorWorkflow()
            result = workflow.execute({"user_id": regular_user.id, "days": 30})

    assert result["user_id"] == regular_user.id
    assert "shirts" in result["purchase_categories"]
    assert cache.get(f"analytics:report:user:{regular_user.id}") is not None


@pytest.mark.django_db
def test_product_performance_workflow_caches_report():
    """ProductPerformanceWorkflow should cache a report under analytics:report:product:{product_id}."""
    product_id = 7
    cache.delete(f"analytics:report:product:{product_id}")

    with patch("apps.ai.workflows.base.BaseWorkflow") as mock_base:
        base_instance = MagicMock()
        base_instance.start_execution.return_value = "test-exec-id"
        base_instance.complete_execution.return_value = None
        mock_base.return_value = base_instance

        with patch(
            "apps.ai.database.access_layer.FashionistarDatabaseLayer"
        ) as mock_db:
            instance = MagicMock()
            instance.get_product_full.return_value = {
                "name": "Test Product",
                "category": "Shirts",
                "view_count": 100,
                "sales_count": 5,
                "average_rating": 4.5,
                "stock_quantity": 20,
            }
            mock_db.return_value = instance

            workflow = ProductPerformanceWorkflow()
            result = workflow.execute({"product_id": product_id, "days": 30})

    assert result["product_id"] == product_id
    assert result["name"] == "Test Product"
    assert cache.get(f"analytics:report:product:{product_id}") is not None


@pytest.mark.django_db
def test_vendor_performance_workflow_caches_report():
    """VendorPerformanceWorkflow should cache a report under analytics:report:vendor:{vendor_id}."""
    vendor_id = 3
    cache.delete(f"analytics:report:vendor:{vendor_id}")

    with patch("apps.ai.workflows.base.BaseWorkflow") as mock_base:
        base_instance = MagicMock()
        base_instance.start_execution.return_value = "test-exec-id"
        base_instance.complete_execution.return_value = None
        mock_base.return_value = base_instance

        with patch(
            "apps.ai.database.access_layer.FashionistarDatabaseLayer"
        ) as mock_db:
            instance = MagicMock()
            instance.get_all_vendor_stats.return_value = [
                {"vendor_id": vendor_id, "gmv": 1000, "total_sales": 10}
            ]
            mock_db.return_value = instance

            workflow = VendorPerformanceWorkflow()
            result = workflow.execute({"vendor_id": vendor_id, "days": 30})

    assert result["vendor_id"] == vendor_id
    assert result["gmv"] == 1000
    assert cache.get(f"analytics:report:vendor:{vendor_id}") is not None
