"""
Tests for analytics rate limiting (Phase 7.6 verification).

Verifies that throttle decorators are applied to analytics endpoints
using UserBurstThrottle and UserSustainedThrottle.
"""

from __future__ import annotations

import pytest
import inspect
from unittest.mock import MagicMock


@pytest.mark.django_db
class TestAnalyticsRateLimiting:
    """Verify rate limiting is applied to analytics endpoints."""

    def _get_throttle_from_endpoint(self, func):
        """Extract throttle class names from endpoint decorator."""
        # The throttle is applied via @router.get(throttle=...)
        # We can check the function's __wrapped__ or the router's route config
        # For Ninja routes, the throttle is stored in the route definition
        source = inspect.getsource(func)
        return source

    def test_user_activity_has_throttle(self):
        """User activity endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_user_activity

        source = self._get_throttle_from_endpoint(get_user_activity)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_metrics_has_throttle(self):
        """Metrics endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_metrics

        source = self._get_throttle_from_endpoint(get_metrics)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_realtime_has_throttle(self):
        """Realtime endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_realtime_analytics

        source = self._get_throttle_from_endpoint(get_realtime_analytics)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_performance_metrics_has_throttle(self):
        """Performance metrics endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_performance_metrics

        source = self._get_throttle_from_endpoint(get_performance_metrics)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_business_metrics_has_throttle(self):
        """Business metrics endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_business_metrics

        source = self._get_throttle_from_endpoint(get_business_metrics)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_alerts_has_throttle(self):
        """Alerts endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_alerts

        source = self._get_throttle_from_endpoint(get_alerts)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_rollups_has_throttle(self):
        """Rollups endpoint has throttle decorator."""
        from apps.analytics.apis.async_.analytics_views import get_metric_rollups

        source = self._get_throttle_from_endpoint(get_metric_rollups)
        assert "throttle" in source or "UserBurstThrottle" in source

    def test_throttle_imports_present(self):
        """Throttle classes are imported in analytics_views."""
        import apps.analytics.apis.async_.analytics_views as views

        assert hasattr(views, "UserBurstThrottle") or "UserBurstThrottle" in dir(views)
        assert hasattr(views, "UserSustainedThrottle") or "UserSustainedThrottle" in dir(views)
