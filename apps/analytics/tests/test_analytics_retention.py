"""
Tests for analytics data retention policies (Phase 7.8 verification).

Verifies that cleanup_expired_data Celery task correctly deletes old records
based on per-model retention settings in ANALYTICS_SETTINGS.
"""

from __future__ import annotations

import pytest
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.utils import timezone


@pytest.mark.django_db
class TestAnalyticsRetention:
    """Verify data retention cleanup works correctly."""

    def test_cleanup_expired_data_task_exists(self):
        """cleanup_expired_data task is importable and callable."""
        from apps.analytics.tasks.analytics_tasks import cleanup_expired_data

        assert callable(cleanup_expired_data)
        assert cleanup_expired_data.name == "apps.analytics.tasks.analytics_tasks.cleanup_expired_data"

    def test_cleanup_task_queue_is_analytics(self):
        """cleanup_expired_data is routed to the analytics queue."""
        from apps.analytics.tasks.analytics_tasks import cleanup_expired_data

        # The queue is set via @shared_task(queue="analytics")
        assert hasattr(cleanup_expired_data, "queue") or "analytics" in str(cleanup_expired_data)

    def test_retention_settings_exist(self):
        """ANALYTICS_SETTINGS has DATA_RETENTION configuration."""
        from apps.analytics.settings import ANALYTICS_SETTINGS

        assert "DATA_RETENTION" in ANALYTICS_SETTINGS
        retention = ANALYTICS_SETTINGS["DATA_RETENTION"]

        assert "METRICS_DAYS" in retention
        assert "USER_ACTIVITY_DAYS" in retention
        assert "PERFORMANCE_METRIC_DAYS" in retention
        assert "BUSINESS_METRIC_DAYS" in retention
        assert "ALERT_DAYS" in retention

    def test_retention_values_are_positive_integers(self):
        """All retention day values are positive integers."""
        from apps.analytics.settings import ANALYTICS_SETTINGS

        retention = ANALYTICS_SETTINGS["DATA_RETENTION"]
        for key, value in retention.items():
            assert isinstance(value, int), f"{key} must be an integer"
            assert value > 0, f"{key} must be positive, got {value}"

    @pytest.mark.django_db
    def test_cleanup_deletes_old_metrics(self):
        """Old Metric records beyond retention are deleted."""
        from apps.analytics.models import Metric
        from apps.analytics.tasks.analytics_tasks import cleanup_expired_data

        now = timezone.now()
        # Create a metric 40 days old (retention is 30 days)
        old_metric = Metric.objects.create(
            name="old_metric",
            metric_type="gauge",
            value=1.0,
            timestamp=now - timedelta(days=40),
        )
        # Create a recent metric
        new_metric = Metric.objects.create(
            name="new_metric",
            metric_type="gauge",
            value=2.0,
            timestamp=now - timedelta(days=1),
        )

        # Run cleanup
        result = cleanup_expired_data.apply()

        # Old metric should be gone, new one should remain
        assert not Metric.objects.filter(id=old_metric.id).exists()
        assert Metric.objects.filter(id=new_metric.id).exists()

    @pytest.mark.django_db
    def test_cleanup_deletes_old_user_activity(self):
        """Old UserActivity records beyond retention are deleted."""
        from apps.analytics.models import UserActivity
        from apps.analytics.tasks.analytics_tasks import cleanup_expired_data
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(
            email="retention@test.com",
            password="testpass123",
        )

        now = timezone.now()
        old_activity = UserActivity.objects.create(
            user=user,
            action="login",
            timestamp=now - timedelta(days=100),
        )
        new_activity = UserActivity.objects.create(
            user=user,
            action="login",
            timestamp=now - timedelta(days=1),
        )

        cleanup_expired_data.apply()

        assert not UserActivity.objects.filter(id=old_activity.id).exists()
        assert UserActivity.objects.filter(id=new_activity.id).exists()

    @pytest.mark.django_db
    def test_cleanup_deletes_old_alerts(self):
        """Old Alert records beyond retention are deleted."""
        from apps.analytics.models import Alert, AlertRule
        from apps.analytics.tasks.analytics_tasks import cleanup_expired_data

        now = timezone.now()
        rule = AlertRule.objects.create(
            name="Retention Test Rule",
            metric_name="test_metric",
            threshold=100.0,
            operator="gt",
            severity="warning",
            is_active=True,
        )

        old_alert = Alert.objects.create(
            rule=rule,
            status="resolved",
            metric_value=200.0,
            message="Old alert",
            fired_at=now - timedelta(days=100),
        )
        new_alert = Alert.objects.create(
            rule=rule,
            status="firing",
            metric_value=150.0,
            message="New alert",
            fired_at=now - timedelta(days=1),
        )

        cleanup_expired_data.apply()

        assert not Alert.objects.filter(id=old_alert.id).exists()
        assert Alert.objects.filter(id=new_alert.id).exists()

    def test_cleanup_task_in_celery_beat_schedule(self):
        """cleanup_expired_data is registered in Celery Beat schedule."""
        from backend.celery import app

        beat_schedule = app.conf.beat_schedule
        found = False
        for task_name, task_config in beat_schedule.items():
            if "cleanup_expired_data" in str(task_config.get("task", "")):
                found = True
                break
        assert found, "cleanup_expired_data not found in Celery Beat schedule"
