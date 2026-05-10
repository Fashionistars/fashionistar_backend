# apps/notification/apis/async_/notification_views.py
"""
Notification Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/notifications/

Architecture:
  ─ Read endpoints → async selectors (Django 6.0 native ORM).
  ─ Mutation endpoints live on the DRF sync surface only.
  ─ asyncio.gather() used for concurrent feed + count fetch.

IMPORTANT:
  sync_to_async is BANNED. Do not add writes to this router.
  Reference: https://docs.djangoproject.com/en/6.0/topics/async/

Dual-Channel Strategy:
  DRF (sync)   → REST polling for notification feed.
  Ninja (async) → Fast badge count + async feed (SSE-compatible polling).
  Future: WebSocket push via Django Channels for true real-time.
"""

import asyncio
import logging
from typing import Optional

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.notification.selectors import (
    aget_user_notifications,
    aget_unread_count,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Notifications — Async"])


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class NotificationOut(Schema):
    id:                str
    notification_type: str
    channel:           str
    title:             str
    body:              str
    metadata:          dict
    is_read:           bool
    sent_at:           Optional[str] = None
    read_at:           Optional[str] = None
    created_at:        str

    @classmethod
    def from_notif(cls, n) -> "NotificationOut":
        return cls(
            id=str(n.id),
            notification_type=n.notification_type,
            channel=n.channel,
            title=n.title,
            body=n.body,
            metadata=n.metadata or {},
            is_read=n.is_read,
            sent_at=n.sent_at.isoformat() if n.sent_at else None,
            read_at=n.read_at.isoformat() if n.read_at else None,
            created_at=n.created_at.isoformat(),
        )


class NotificationFeedOut(Schema):
    unread_count:  int
    total:         int
    notifications: list[NotificationOut]


class UnreadCountOut(Schema):
    unread_count: int


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/feed/", response=NotificationFeedOut)
async def get_notification_feed(
    request,
    unread_only: bool = False,
    channel: str = "in_app",
):
    """
    GET /api/v1/ninja/notifications/feed/

    Async notification feed + unread count gathered concurrently.
    Supports ?unread_only=true and ?channel=<channel> query params.

    Dual-channel strategy: replaces the DRF polling endpoint for high-frequency
    clients (mobile apps, dashboard widgets) that need sub-50ms responses.
    """
    user = request.auth
    try:
        notifications, unread_count = await asyncio.gather(
            aget_user_notifications(
                user_id=user.id,
                channel=channel,
                unread_only=unread_only,
                limit=50,
            ),
            aget_unread_count(user_id=user.id),
        )
    except Exception:
        logger.exception(
            "get_notification_feed: error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Failed to fetch notifications.")

    return NotificationFeedOut(
        unread_count=unread_count,
        total=len(notifications),
        notifications=[NotificationOut.from_notif(n) for n in notifications],
    )


@router.get("/unread-count/", response=UnreadCountOut)
async def get_unread_count_endpoint(request):
    """
    GET /api/v1/ninja/notifications/unread-count/

    Lightweight async badge count endpoint.
    Polled by frontend every 30s as SSE-compatible REST fallback.
    Returns a single integer — designed for high-frequency polling
    without the overhead of full feed serialization.
    """
    user = request.auth
    try:
        count = await aget_unread_count(user_id=user.id)
    except Exception:
        logger.exception(
            "get_unread_count_endpoint: error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Failed to fetch unread count.")
    return UnreadCountOut(unread_count=count)
