"""
Tests for apps.analytics.services.realtime_service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.analytics.services.realtime_service import (
    RealtimeAnalyticsService,
    RealtimeEvent,
    publish_analytics_event,
)


@pytest.mark.django_db
def test_publish_analytics_event_with_redis():
    """publish_analytics_event should publish to the Redis stream when Redis is available."""
    mock_redis = MagicMock()
    with patch(
        "apps.analytics.services.realtime_service.RealtimeAnalyticsService._get_redis_client",
        return_value=mock_redis,
    ):
        result = publish_analytics_event(
            event_type="page_view",
            user_id="42",
            endpoint="/home",
            response_time_ms=100,
            status_code=200,
        )

    assert result is True
    mock_redis.xadd.assert_called_once()


@pytest.mark.django_db
def test_realtime_service_get_aggregated_snapshot():
    """get_aggregated_snapshot should return cached snapshot or an empty snapshot."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = '{"event_count": 5, "unique_users": 2}'
    service = RealtimeAnalyticsService(redis_client=mock_redis)

    snapshot = service.get_aggregated_snapshot(window_seconds=60)
    assert snapshot["event_count"] == 5
    assert snapshot["unique_users"] == 2


@pytest.mark.django_db
def test_realtime_service_set_aggregated_snapshot():
    """set_aggregated_snapshot should write the snapshot to Redis with a TTL."""
    mock_redis = MagicMock()
    service = RealtimeAnalyticsService(redis_client=mock_redis)

    service.set_aggregated_snapshot({"event_count": 10}, ttl=120)
    mock_redis.setex.assert_called_once()


@pytest.mark.django_db
def test_realtime_service_consume_pending():
    """consume_pending should parse Redis stream entries into RealtimeEvent objects."""
    mock_redis = MagicMock()
    mock_redis.xreadgroup.return_value = [
        [
            "stream-id",
            [
                [
                    "msg-id",
                    {
                        "event_type": "api_call",
                        "timestamp": "1234567890.0",
                        "user_id": "1",
                        "session_id": "abc",
                        "endpoint": "/api",
                        "response_time_ms": "50",
                        "status_code": "200",
                        "metadata": "{}",
                    },
                ]
            ],
        ]
    ]
    service = RealtimeAnalyticsService(redis_client=mock_redis)

    events = service.consume_pending("consumer-1")
    assert len(events) == 1
    assert events[0].event_type == "api_call"
    assert events[0].response_time_ms == 50
