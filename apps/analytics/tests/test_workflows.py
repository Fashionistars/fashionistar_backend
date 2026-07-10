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


@pytest.fixture
def workflow():
    """Return a fresh AnalyticsWorkflow instance."""
    return AnalyticsWorkflow()


@pytest.mark.django_db
def test_analytics_workflow_execute_returns_report(workflow, regular_user):
    """The workflow should return a report dict containing expected keys."""
    with patch("apps.analytics.workflows.analytics.BaseWorkflow") as mock_base:
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
                                    workflow, "_persist_report", side_effect=lambda s: {**s, "report": {}}
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

    # Verify cache is populated
    cached = cache.get(report["cache_key"])
    assert cached is not None
    assert json.loads(cached)["scope"] == "platform"


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

    with patch("apps.analytics.workflows.analytics.generate_llm_insights") as mock_generate:
        mock_generate.return_value = "Insight text"
        new_state = workflow._generate_llm_insights(state)

    assert new_state["llm_insights"] == "Insight text"
    mock_generate.assert_called_once()
