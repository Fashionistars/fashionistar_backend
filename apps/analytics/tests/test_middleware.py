"""
Tests for apps.analytics.middleware.user_activity.UserActivityTrackingMiddleware.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from apps.analytics.middleware.user_activity import UserActivityTrackingMiddleware


@pytest.mark.django_db
def test_middleware_passes_through_for_unauthenticated_user():
    """Middleware should skip tracking for unauthenticated users."""
    factory = RequestFactory()
    request = factory.get("/api/v1/test")
    request.user = MagicMock()
    request.user.is_authenticated = False

    response = HttpResponse(status=200)
    middleware = UserActivityTrackingMiddleware(get_response=MagicMock(return_value=response))
    result = middleware(request)

    assert result.status_code == 200


@pytest.mark.django_db
def test_middleware_passes_through_for_get_requests():
    """Middleware should skip tracking for GET requests (only tracks POST/PUT/PATCH/DELETE)."""
    factory = RequestFactory()
    request = factory.get("/api/v1/test")
    request.user = MagicMock()
    request.user.is_authenticated = True
    request.user.id = 42

    response = HttpResponse(status=200)
    middleware = UserActivityTrackingMiddleware(get_response=MagicMock(return_value=response))
    result = middleware(request)

    assert result.status_code == 200


@pytest.mark.django_db
def test_middleware_records_post_activity():
    """Middleware should record activity for authenticated POST requests."""
    factory = RequestFactory()
    request = factory.post("/api/v1/products/")
    request.user = MagicMock()
    request.user.is_authenticated = True
    request.user.id = 42
    request.session = MagicMock()
    request.session.session_key = "test-session"

    response = HttpResponse(status=201)
    middleware = UserActivityTrackingMiddleware(get_response=MagicMock(return_value=response))

    with patch("apps.analytics.tasks.record_user_activity_async") as mock_task:
        result = middleware(request)

    assert result.status_code == 201
    mock_task.delay.assert_called_once()
    call_kwargs = mock_task.delay.call_args.kwargs
    assert call_kwargs["user_id"] == 42
    assert call_kwargs["action"] == "create"


@pytest.mark.django_db
def test_middleware_skips_error_responses():
    """Middleware should skip tracking for error responses (status >= 400)."""
    factory = RequestFactory()
    request = factory.post("/api/v1/products/")
    request.user = MagicMock()
    request.user.is_authenticated = True
    request.user.id = 42

    response = HttpResponse(status=500)
    middleware = UserActivityTrackingMiddleware(get_response=MagicMock(return_value=response))

    with patch("apps.analytics.tasks.record_user_activity_async") as mock_task:
        result = middleware(request)

    assert result.status_code == 500
    mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_middleware_get_client_ip():
    """Middleware should correctly extract client IP from request."""
    factory = RequestFactory()
    request = factory.get("/api/v1/test", HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2")
    request.user = MagicMock()
    request.user.is_authenticated = False

    response = HttpResponse(status=200)
    middleware = UserActivityTrackingMiddleware(get_response=MagicMock(return_value=response))

    ip = middleware._get_client_ip(request)
    assert ip == "10.0.0.1"
