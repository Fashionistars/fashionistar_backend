# apps/notification/realtime.py
"""
Post-commit fanout helpers for real-time notification push.

All functions are fail-safe: a Redis / channel_layer outage must NEVER
propagate an exception to the caller (admin save, service method, etc.).

Usage:
    from apps.notification.realtime import (
        push_unread_badge_count,
        push_new_notification,
    )

    # After creating a Notification row:
    push_new_notification(notification_instance)

    # After marking notifications read (clears badge):
    push_unread_badge_count(user_id)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.notification.models import Notification, NotificationChannel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _get_layer():
    """Return the channel layer or None if Redis is unavailable."""
    try:
        return get_channel_layer()
    except Exception as exc:
        logger.debug("realtime: get_channel_layer failed: %s", exc)
        return None


def push_unread_badge_count(user_id) -> None:
    """
    Push the latest unread in-app notification count to a user's socket group.

    Called after:
      - A new notification is created for the user.
      - The user marks one or all notifications read.
      - Any service that mutates the user's notification state.

    Fails silently when Redis / channel_layer is unavailable.
    """
    channel_layer = _get_layer()
    if channel_layer is None:
        return

    try:
        unread_count = Notification.objects.filter(
            recipient_id=user_id,
            channel=NotificationChannel.IN_APP,
            read_at__isnull=True,
        ).count()

        async_to_sync(channel_layer.group_send)(
            f"notification_user_{user_id}",
            {
                "type": "notification.badge",
                "payload": {"unread_count": unread_count},
            },
        )
        logger.debug("push_unread_badge_count: user=%s unread=%s", user_id, unread_count)
    except Exception as exc:
        logger.debug("push_unread_badge_count: failed for user=%s: %s", user_id, exc)


def push_new_notification(notification: Notification) -> None:
    """
    Push a newly created Notification to the recipient's socket group.

    The consumer's ``notification_new`` handler forwards the payload to
    every open browser tab of the same user so the notification feed
    updates instantly without a REST poll.

    Payload mirrors the NotificationSchema used by the frontend:
      id, title, body, notification_type, channel, is_read, created_at

    Fails silently when Redis / channel_layer is unavailable.
    """
    channel_layer = _get_layer()
    if channel_layer is None:
        return

    try:
        user_id = str(notification.recipient_id)
        payload = {
            "id": str(notification.pk),
            "title": notification.title,
            "body": notification.body,
            "notification_type": notification.notification_type,
            "channel": notification.channel,
            "is_read": bool(notification.is_read),
            "is_sent": bool(notification.is_sent),
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
            "created_at": (
                notification.created_at.isoformat()
                if notification.created_at
                else None
            ),
        }
        async_to_sync(channel_layer.group_send)(
            f"notification_user_{user_id}",
            {"type": "notification.new", "payload": payload},
        )
        # Also refresh the badge count so the number increments in real time.
        push_unread_badge_count(user_id)
        logger.debug("push_new_notification: user=%s notification=%s", user_id, notification.pk)
    except Exception as exc:
        logger.debug("push_new_notification: failed for notification=%s: %s", notification.pk, exc)
