"""
Tests for apps.audit_logs.services.analytics.analytics_audit.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService


@pytest.mark.django_db
def test_log_metric_recorded():
    """log_metric_recorded should delegate to AuditService.log."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_metric_recorded(
            actor=MagicMock(), metric_name="m1", metric_type="gauge", value=1.0
        )
        mock_log.assert_called_once()
        details = mock_log.call_args.kwargs["details"]
        assert details["metric_name"] == "m1"
        assert details["value"] == 1.0


@pytest.mark.django_db
def test_log_user_activity_logged():
    """log_user_activity_logged should include user_id, action, and resource."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_user_activity_logged(
            actor=MagicMock(), user_id="42", action="login", resource="auth"
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["user_id"] == "42"
        assert details["action"] == "login"
        assert details["resource"] == "auth"


@pytest.mark.django_db
def test_log_performance_metric_recorded():
    """log_performance_metric_recorded should record endpoint and status code."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_performance_metric_recorded(
            actor=MagicMock(), endpoint="/api/v1/test", response_time_ms=120, status_code=200
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["endpoint"] == "/api/v1/test"
        assert details["status_code"] == 200


@pytest.mark.django_db
def test_log_business_metric_updated():
    """log_business_metric_updated should record metric name, value, and period."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_business_metric_updated(
            actor=MagicMock(), metric_name="gmv", value=1000.0, period="daily"
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["metric_name"] == "gmv"
        assert details["period"] == "daily"


@pytest.mark.django_db
def test_log_alert_triggered():
    """log_alert_triggered should record alert rule, metric value, and severity."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_alert_triggered(
            actor=MagicMock(), alert_rule_id=7, metric_value=99.0, severity="high"
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["alert_rule_id"] == 7
        assert details["severity"] == "high"


@pytest.mark.django_db
def test_log_alert_resolved():
    """log_alert_resolved should record alert id and resolution notes."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_alert_resolved(
            actor=MagicMock(), alert_id=5, resolution_notes="auto-resolved"
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["alert_id"] == 5
        assert details["resolution_notes"] == "auto-resolved"


@pytest.mark.django_db
def test_log_analytics_query_executed():
    """log_analytics_query_executed should record query type and time range."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_analytics_query_executed(
            actor=MagicMock(), query_type="dashboard", time_range="24h"
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["query_type"] == "dashboard"
        assert details["time_range"] == "24h"


@pytest.mark.django_db
def test_log_metric_aggregation_executed():
    """log_metric_aggregation_executed should record window and record count."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_metric_aggregation_executed(
            actor=MagicMock(), aggregation_window="5m", record_count=42
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["aggregation_window"] == "5m"
        assert details["record_count"] == 42


@pytest.mark.django_db
def test_log_data_retention_applied():
    """log_data_retention_applied should record retention days and deleted count."""
    with patch("apps.audit_logs.services.analytics.analytics_audit.AuditService.log") as mock_log:
        AnalyticsAuditService.log_data_retention_applied(
            actor=MagicMock(), retention_days=90, deleted_count=100
        )
        details = mock_log.call_args.kwargs["details"]
        assert details["retention_days"] == 90
        assert details["deleted_count"] == 100
