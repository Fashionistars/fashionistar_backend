"""
Tests for analytics RBAC permissions (Phase 7.5 verification).

Verifies that staff/admin checks are enforced on sensitive endpoints
and that regular users receive 403 Forbidden.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.analytics.tests.conftest import *


@pytest.mark.django_db
class TestAnalyticsPermissions:
    """Verify RBAC is enforced on analytics endpoints."""

    @pytest.mark.asyncio
    async def test_user_activity_requires_staff(self, regular_user):
        """Regular (non-staff) users cannot access user-activity endpoint."""
        from apps.analytics.apis.async_.analytics_views import get_user_activity
        from ninja.errors import HttpError

        request = MagicMock()
        request.auth = regular_user
        request.GET = {}

        with pytest.raises(HttpError) as exc_info:
            await get_user_activity(request, page=1, page_size=20)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_user_activity_allows_staff(self, staff_user):
        """Staff users can access user-activity endpoint."""
        from apps.analytics.apis.async_.analytics_views import get_user_activity

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
                mock_sel.get_queryset.return_value = MagicMock()
                result = await get_user_activity(request, page=1, page_size=20)

            assert result is not None

    @pytest.mark.asyncio
    async def test_realtime_requires_staff(self, regular_user):
        """Regular users cannot access realtime analytics."""
        from apps.analytics.apis.async_.analytics_views import get_realtime_analytics
        from ninja.errors import HttpError

        request = MagicMock()
        request.auth = regular_user

        with pytest.raises(HttpError) as exc_info:
            await get_realtime_analytics(request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_dashboard_requires_admin(self, regular_user):
        """Regular users cannot access dashboard endpoints."""
        from apps.analytics.apis.async_.dashboard_views import get_system_overview
        from ninja.errors import HttpError

        request = MagicMock()
        request.auth = regular_user

        with pytest.raises(HttpError) as exc_info:
            await get_system_overview(request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_rollups_requires_staff(self, regular_user):
        """Regular users cannot access rollups endpoint."""
        from apps.analytics.apis.async_.analytics_views import get_metric_rollups
        from ninja.errors import HttpError

        request = MagicMock()
        request.auth = regular_user

        with pytest.raises(HttpError) as exc_info:
            await get_metric_rollups(request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_platform_analytics_requires_staff(self, regular_user):
        """Regular users cannot access platform analytics."""
        from apps.analytics.apis.async_.analytics_views import get_platform_analytics
        from ninja.errors import HttpError

        request = MagicMock()
        request.auth = regular_user

        with pytest.raises(HttpError) as exc_info:
            await get_platform_analytics(request, days=7)

        assert exc_info.value.status_code == 403
