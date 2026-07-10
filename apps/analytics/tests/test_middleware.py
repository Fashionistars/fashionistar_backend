"""
Tests for apps.analytics.middleware.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, HttpResponse

from apps.analytics.middleware import AnalyticsMiddleware


@pytest.mark.django_db
def test_analytics_middleware_records_sync_request():
    """Analytics middleware should record sync request metrics and publish a real-time event."""
    request = HttpRequest()
    request.method = "GET"
    request.path = "/api/v1/test"
    request.user = MagicMock()
    request.user.is_authenticated = True
    request.user.id = 42

    response = HttpResponse(status=200)
    get_response = MagicMock(return_value=response)

    with patch("apps.analytics.middleware.publish_analytics_event") as mock_publish, patch(
        "apps.analytics.middleware.get_metrics_service"
    ) as mock_metrics:
        middleware = AnalyticsMiddleware(get_response=get_response)
        middleware.is_async = False
        result = middleware(request)

    assert result.status_code == 200
    mock_publish.assert_called_once()
    mock_metrics.return_value.record_query.assert_called_once()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_analytics_middleware_records_async_request():
    """Analytics middleware should record async request metrics and publish a real-time event."""
    request = HttpRequest()
    request.method = "POST"
    request.path = "/api/v1/async"
    request.user = MagicMock()
    request.user.is_authenticated = False

    response = HttpResponse(status=201)
    get_response = MagicMock(return_value=response)

    with patch("apps.analytics.middleware.publish_analytics_event") as mock_publish, patch(
        "apps.analytics.middleware.get_metrics_service"
    ) as mock_metrics:
        middleware = AnalyticsMiddleware(get_response=get_response)
        middleware.is_async = True
        result = await middleware(request)

    assert result.status_code == 201
    mock_publish.assert_called_once()
    mock_metrics.return_value.record_query.assert_called_once()
