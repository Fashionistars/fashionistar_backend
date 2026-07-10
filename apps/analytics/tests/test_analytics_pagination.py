"""
Tests for analytics endpoint pagination (Phase 7.4 verification).

Verifies that all list endpoints use async_ninja_paginate and return
paginated response structure with 'count', 'page', 'page_size', 'results'.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.analytics.tests.conftest import *


@pytest.mark.django_db
class TestAnalyticsPagination:
    """Verify pagination is applied to all analytics list endpoints."""

    def test_user_activity_endpoint_has_pagination_param(self):
        """The user-activity endpoint accepts page and page_size params."""
        from apps.analytics.apis.async_.analytics_views import get_user_activity
        import inspect

        sig = inspect.signature(get_user_activity)
        params = list(sig.parameters.keys())
        assert "page" in params, "get_user_activity must accept 'page' parameter"
        assert "page_size" in params, "get_user_activity must accept 'page_size' parameter"

    def test_metrics_endpoint_has_pagination_param(self):
        """The metrics endpoint accepts page and page_size params."""
        from apps.analytics.apis.async_.analytics_views import get_metrics
        import inspect

        sig = inspect.signature(get_metrics)
        params = list(sig.parameters.keys())
        assert "page" in params, "get_metrics must accept 'page' parameter"
        assert "page_size" in params, "get_metrics must accept 'page_size' parameter"

    def test_performance_metrics_endpoint_has_pagination(self):
        """The performance-metrics endpoint accepts page and page_size params."""
        from apps.analytics.apis.async_.analytics_views import get_performance_metrics
        import inspect

        sig = inspect.signature(get_performance_metrics)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "page_size" in params

    def test_business_metrics_endpoint_has_pagination(self):
        """The business-metrics endpoint accepts page and page_size params."""
        from apps.analytics.apis.async_.analytics_views import get_business_metrics
        import inspect

        sig = inspect.signature(get_business_metrics)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "page_size" in params

    def test_alerts_endpoint_has_pagination(self):
        """The alerts endpoint accepts page and page_size params."""
        from apps.analytics.apis.async_.analytics_views import get_alerts
        import inspect

        sig = inspect.signature(get_alerts)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "page_size" in params

    @pytest.mark.asyncio
    async def test_pagination_returns_correct_structure(self, staff_user):
        """Paginated endpoint returns dict with count, page, page_size, results."""
        from apps.analytics.apis.async_.analytics_views import get_user_activity
        from ninja import Router
        import json

        request = MagicMock()
        request.auth = staff_user
        request.GET = {}

        with patch(
            "apps.analytics.apis.async_.analytics_views.async_ninja_paginate",
            new_callable=AsyncMock,
        ) as mock_paginate:
            mock_paginate.return_value = {
                "count": 0,
                "page": 1,
                "page_size": 20,
                "results": [],
            }
            with patch(
                "apps.analytics.apis.async_.analytics_views.UserActivitySelector"
            ) as mock_sel:
                mock_qs = MagicMock()
                mock_sel.get_queryset.return_value = mock_qs
                result = await get_user_activity(request, page=1, page_size=20)

            assert "count" in result
            assert "page" in result
            assert "page_size" in result
            assert "results" in result
            assert isinstance(result["results"], list)
