# apps/measurements/ws/scan_consumer.py
"""
GAP-4 FIX: ScanProgressConsumer — Django Channels WebSocket consumer.

Replaces 2-second polling (useScanSession.ts) with real-time push events.
One WebSocket connection per scan session; the Celery task publishes progress
to a Redis channel and this consumer forwards events to the browser.

WebSocket URL:
    ws://<host>/ws/scan/<session_id>/

Query-string auth:
    ?token=<JWT_access_token>   (verified by JWTQueryAuthMiddleware)

Event flow:
    Browser connects
        ↓
    Consumer subscribes to Redis channel "scan:<session_id>"
        ↓
    Celery MeasurementWorkflow publishes events at each node:
        {"type": "scan.update", "event": "processing_started",  "data": {...}}
        {"type": "scan.update", "event": "measurements_extracted", "data": {...}}
        {"type": "scan.update", "event": "profile_saved",      "data": {...}}
        {"type": "scan.update", "event": "completed",           "data": {...}}
        {"type": "scan.update", "event": "failed",              "data": {...}}
        ↓
    Consumer forwards each event as JSON to the WebSocket client

Event payload schema:
    {
        "event": str,              # "processing_started" | "measurements_extracted" | ...
        "session_id": str,
        "status": str,             # "processing" | "completed" | "failed"
        "data": {
            "quality_score": float | None,
            "measurements_cm": dict | None,
            "plausibility_warnings": list[str],
            "correction_applied": str,
            "bmi": float | None,
            "profile_id": str | None,
            "error_message": str | None,
        }
    }
"""

import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)

# Redis channel name pattern  →  scan:<session_uuid>
SCAN_CHANNEL_PREFIX = "scan"


class ScanProgressConsumer(AsyncJsonWebsocketConsumer):
    """
    Async WebSocket consumer for real-time scan progress events.

    Lifecycle:
        connect()     → validate session ownership → subscribe to Redis group
        receive_json()→ ignored (client never sends data; read-only socket)
        disconnect()  → unsubscribe from Redis group
    """

    async def connect(self):
        """Accept the connection and subscribe to this session's channel group."""
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.user       = self.scope.get("user")
        self.group_name = f"{SCAN_CHANNEL_PREFIX}.{self.session_id}"

        # Validate user is authenticated (JWTQueryAuthMiddleware handles token)
        if not self.user or not self.user.is_authenticated:
            logger.warning(
                "[ScanProgressConsumer] Unauthenticated connection rejected session=%s",
                self.session_id
            )
            await self.close(code=4001)
            return

        # Validate user owns the session (async DB check)
        owns_session = await self._check_session_ownership()
        if not owns_session:
            logger.warning(
                "[ScanProgressConsumer] Unauthorized session=%s user=%s",
                self.session_id, self.user.pk
            )
            await self.close(code=4003)
            return

        # Subscribe to the scan's Redis channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send current status immediately so client doesn't have to wait for an event
        await self._send_current_status()

        logger.info(
            "[ScanProgressConsumer] Connected session=%s user=%s group=%s",
            self.session_id, self.user.pk, self.group_name
        )

    async def disconnect(self, code):
        """Unsubscribe from the Redis group on disconnect."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.debug(
                "[ScanProgressConsumer] Disconnected session=%s code=%s",
                self.session_id, code
            )

    async def receive_json(self, content, **kwargs):
        """Client-to-server messages are not expected; silently ignore."""
        pass

    # ── Channel layer message handlers ──────────────────────────────────────────

    async def scan_update(self, event: dict):
        """
        Receive a scan.update message from the channel layer (published by Celery)
        and forward it to the WebSocket client.

        Channel layer message format:
            {
                "type": "scan.update",
                "event": "completed",
                "session_id": "...",
                "status": "completed",
                "data": { ... }
            }
        """
        try:
            await self.send_json({
                "event":      event.get("event"),
                "session_id": event.get("session_id", self.session_id),
                "status":     event.get("status"),
                "data":       event.get("data", {}),
            })
        except Exception as exc:
            logger.warning(
                "[ScanProgressConsumer] Failed to forward scan.update: %s", exc
            )

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _check_session_ownership(self) -> bool:
        """Return True if the authenticated user owns this scan session."""
        from channels.db import database_sync_to_async
        from apps.measurements.models.scan import BodyScanSession

        @database_sync_to_async
        def check():
            return BodyScanSession.objects.filter(
                session_id=self.session_id,
                owner=self.user,
            ).exists()

        try:
            return await check()
        except Exception as exc:
            logger.warning("[ScanProgressConsumer] _check_session_ownership error: %s", exc)
            return False

    async def _send_current_status(self):
        """Send the current session status as the first event on connect."""
        from channels.db import database_sync_to_async
        from apps.measurements.models.scan import BodyScanSession

        @database_sync_to_async
        def get_status():
            try:
                session = BodyScanSession.objects.filter(
                    session_id=self.session_id
                ).values(
                    "status", "scan_confidence", "extracted_measurements",
                    "plausibility_warnings", "correction_applied", "bmi",
                    "error_message",
                ).first()
                return session
            except Exception:
                return None

        session = await get_status()
        if session:
            await self.send_json({
                "event":      "status_snapshot",
                "session_id": self.session_id,
                "status":     session.get("status", "pending"),
                "data": {
                    "quality_score":          session.get("scan_confidence"),
                    "measurements_cm":        session.get("extracted_measurements"),
                    "plausibility_warnings":  session.get("plausibility_warnings") or [],
                    "correction_applied":     session.get("correction_applied") or "none",
                    "bmi":                    session.get("bmi"),
                    "error_message":          session.get("error_message"),
                },
            })
