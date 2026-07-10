"""
Tests for apps.analytics.services.sentry_service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.analytics.services.sentry_service import AnalyticsSentryService


@pytest.mark.django_db
def test_sentry_service_available_when_sdk_present():
    """is_available should reflect whether sentry_sdk is installed."""
    with patch(
        "apps.analytics.services.sentry_service.SENTRY_AVAILABLE", True
    ):
        assert AnalyticsSentryService.is_available() is True


@pytest.mark.django_db
def test_sentry_service_capture_exception_degrades_gracefully():
    """capture_exception should return None when sentry_sdk is not installed."""
    with patch(
        "apps.analytics.services.sentry_service.SENTRY_AVAILABLE", False
    ):
        result = AnalyticsSentryService.capture_exception(ValueError("boom"))
        assert result is None


@pytest.mark.django_db
def test_sentry_service_capture_exception_with_sdk():
    """capture_exception should call sentry_sdk when available."""
    mock_capture = MagicMock(return_value="event-id")
    with patch(
        "apps.analytics.services.sentry_service.SENTRY_AVAILABLE", True
    ), patch(
        "apps.analytics.services.sentry_service.capture_exception",
        mock_capture,
    ) as _mock_capture, patch(
        "apps.analytics.services.sentry_service.set_tag"
    ) as _mock_tag, patch(
        "apps.analytics.services.sentry_service.set_context"
    ) as _mock_context:
        exc = ValueError("boom")
        result = AnalyticsSentryService.capture_exception(
            exception=exc,
            context={"task": "rollup_1m"},
            tags={"domain": "analytics"},
        )

    assert result == "event-id"
    mock_capture.assert_called_once_with(exc)
