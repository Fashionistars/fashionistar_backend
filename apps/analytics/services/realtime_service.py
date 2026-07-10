# apps/analytics/services/realtime_service.py
"""
Real-time analytics service using Redis Streams.

Produces lightweight analytics events (page views, API calls, errors) to a
Redis Stream and consumes them for dashboard aggregation. WebSocket consumers
can subscribe to the aggregated stream for live updates.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from django.conf import settings
from redis import Redis

logger = logging.getLogger(__name__)

STREAM_KEY = "analytics:events:stream"
CONSUMER_GROUP = "analytics:consumers"
AGGREGATED_KEY = "analytics:realtime:aggregated"
MAX_STREAM_LEN = 10000


@dataclass
class RealtimeEvent:
    """Analytics event emitted for real-time processing."""
    event_type: str
    timestamp: float
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    endpoint: Optional[str] = None
    response_time_ms: Optional[int] = None
    status_code: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class RealtimeAnalyticsService:
    """Redis-Streams-backed real-time analytics service."""

    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis = redis_client
        if self.redis is None:
            self.redis = self._get_redis_client()

    @staticmethod
    def _get_redis_client() -> Redis:
        """Build a Redis client from Django settings."""
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        return Redis.from_url(redis_url, decode_responses=True)

    def publish_event(self, event: RealtimeEvent) -> bool:
        """Publish a single analytics event to the Redis Stream."""
        if not self.redis:
            return False
        try:
            payload = asdict(event)
            payload["metadata"] = json.dumps(payload.get("metadata") or {})
            self.redis.xadd(
                STREAM_KEY,
                payload,
                maxlen=MAX_STREAM_LEN,
                approximate=True,
            )
            return True
        except Exception as exc:
            logger.warning("[RealtimeAnalyticsService] publish failed: %s", exc)
            return False

    def ensure_consumer_group(self) -> None:
        """Create the consumer group if it does not exist."""
        if not self.redis:
            return
        try:
            self.redis.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True
            )
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                logger.warning(
                    "[RealtimeAnalyticsService] group creation failed: %s", exc
                )

    def consume_pending(
        self, consumer_name: str, count: int = 100, block_ms: int = 1000
    ) -> List[RealtimeEvent]:
        """Consume pending events from the Redis Stream for this consumer."""
        if not self.redis:
            return []
        self.ensure_consumer_group()
        try:
            entries = self.redis.xreadgroup(
                CONSUMER_GROUP,
                consumer_name,
                {STREAM_KEY: ">"},
                count=count,
                block=block_ms,
            )
            events = []
            for _stream, messages in entries:
                for _msg_id, fields in messages:
                    event = self._fields_to_event(fields)
                    if event:
                        events.append(event)
            return events
        except Exception as exc:
            logger.warning("[RealtimeAnalyticsService] consume failed: %s", exc)
            return []

    def acknowledge(self, message_ids: List[str]) -> None:
        """Acknowledge processed messages so they are not redelivered."""
        if not self.redis or not message_ids:
            return
        try:
            self.redis.xack(STREAM_KEY, CONSUMER_GROUP, *message_ids)
        except Exception as exc:
            logger.warning("[RealtimeAnalyticsService] ack failed: %s", exc)

    def get_aggregated_snapshot(self, window_seconds: int = 60) -> Dict[str, Any]:
        """Return the latest aggregated real-time snapshot."""
        if not self.redis:
            return self._empty_snapshot(window_seconds)
        try:
            cached = self.redis.get(AGGREGATED_KEY)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("[RealtimeAnalyticsService] snapshot read failed: %s", exc)
        return self._empty_snapshot(window_seconds)

    def set_aggregated_snapshot(self, snapshot: Dict[str, Any], ttl: int = 60) -> None:
        """Cache the aggregated real-time snapshot."""
        if not self.redis:
            return
        try:
            self.redis.setex(AGGREGATED_KEY, ttl, json.dumps(snapshot, default=str))
        except Exception as exc:
            logger.warning("[RealtimeAnalyticsService] snapshot write failed: %s", exc)

    @staticmethod
    def _empty_snapshot(window_seconds: int) -> Dict[str, Any]:
        return {
            "window_seconds": window_seconds,
            "event_count": 0,
            "unique_users": 0,
            "avg_response_time_ms": 0,
            "error_count": 0,
            "generated_at": time.time(),
        }

    @staticmethod
    def _fields_to_event(fields: Dict[str, str]) -> Optional[RealtimeEvent]:
        try:
            return RealtimeEvent(
                event_type=fields.get("event_type", ""),
                timestamp=float(fields.get("timestamp", 0)),
                user_id=fields.get("user_id") or None,
                session_id=fields.get("session_id") or None,
                endpoint=fields.get("endpoint") or None,
                response_time_ms=int(fields["response_time_ms"])
                if fields.get("response_time_ms")
                else None,
                status_code=int(fields["status_code"]) if fields.get("status_code") else None,
                metadata=json.loads(fields.get("metadata", "{}")),
            )
        except Exception as exc:
            logger.warning("[RealtimeAnalyticsService] event parse failed: %s", exc)
            return None


def publish_analytics_event(
    event_type: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    status_code: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Convenience function to publish an analytics event from sync code."""
    service = RealtimeAnalyticsService()
    event = RealtimeEvent(
        event_type=event_type,
        timestamp=time.time(),
        user_id=user_id,
        session_id=session_id,
        endpoint=endpoint,
        response_time_ms=response_time_ms,
        status_code=status_code,
        metadata=metadata,
    )
    return service.publish_event(event)
