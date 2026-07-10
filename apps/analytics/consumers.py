# apps/analytics/consumers.py
"""
WebSocket consumer for real-time analytics dashboards.

Requires Django Channels. If channels is not installed, this module exposes a
fallback stub so imports do not break during django.setup().
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

try:
    from channels.generic.websocket import AsyncJsonWebsocketConsumer
except ImportError:  # pragma: no cover - channels not installed
    AsyncJsonWebsocketConsumer = None  # type: ignore

logger = logging.getLogger(__name__)


if AsyncJsonWebsocketConsumer is not None:
    class AnalyticsRealtimeConsumer(AsyncJsonWebsocketConsumer):
        """Broadcast aggregated real-time analytics to dashboard clients."""

        group_name = "analytics_realtime"

        async def connect(self):
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info("[AnalyticsRealtimeConsumer] client connected")

        async def disconnect(self, close_code):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info("[AnalyticsRealtimeConsumer] client disconnected")

        async def receive_json(self, content: Dict[str, Any], **kwargs):
            """Handle incoming messages (e.g., subscription filters)."""
            message_type = content.get("type", "ping")
            if message_type == "ping":
                await self.send_json({"type": "pong", "timestamp": content.get("timestamp")})

        async def analytics_snapshot(self, event: Dict[str, Any]):
            """Receive broadcast snapshot from channel layer."""
            await self.send_json({
                "type": "analytics_snapshot",
                "data": event.get("data", {}),
            })
else:
    class AnalyticsRealtimeConsumer:  # type: ignore
        """Fallback stub when Django Channels is not installed."""

        def __init__(self, *args, **kwargs):
            logger.warning(
                "[AnalyticsRealtimeConsumer] Django Channels is not installed; "
                "real-time WebSocket consumer is unavailable."
            )
