"""Notification domain audit helper — Wave B13."""
from __future__ import annotations


def log_notification_sent(
    *, actor=None, recipient_id: str, channel: str,
    notification_id: str = "", template: str = ""
) -> None:
    """Record a notification being dispatched to a user.

    Args:
        actor: System or staff actor sending the notification (None for system).
        recipient_id: UnifiedUser PK of the recipient.
        channel: Delivery channel ('email', 'push', 'sms', 'in_app').
        notification_id: Notification PK if persisted.
        template: Template name/slug used.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.NOTIFICATION_SENT,
        event_category=EventCategory.NOTIFICATION,
        action=f"Notification sent: channel={channel} recipient={recipient_id} template={template}",
        actor=actor,
        resource_type="Notification",
        resource_id=notification_id,
        new_values={
            "recipient_id": recipient_id,
            "channel": channel,
            "template": template,
        },
    )


def log_notification_failed(
    *, recipient_id: str, channel: str, error: str, notification_id: str = ""
) -> None:
    """Record a notification delivery failure.

    Args:
        recipient_id: UnifiedUser PK.
        channel: Attempted delivery channel.
        error: Error message from the delivery provider.
        notification_id: Notification PK.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.NOTIFICATION_FAILED,
        event_category=EventCategory.NOTIFICATION,
        action=f"Notification failed: channel={channel} recipient={recipient_id} error={error[:200]}",
        resource_type="Notification",
        resource_id=notification_id,
        severity="error",
        error_message=error,
        new_values={"recipient_id": recipient_id, "channel": channel},
    )


def log_push_token_registered(*, actor, token_id: str, platform: str = "", request=None) -> None:
    """Record a push notification token registration.

    Args:
        actor: The user registering their device token.
        token_id: PushToken PK.
        platform: Device platform ('ios', 'android', 'web').
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.NOTIFICATION_SENT,
        event_category=EventCategory.NOTIFICATION,
        action=f"Push token registered: platform={platform} user={getattr(actor, 'email', str(actor))}",
        actor=actor,
        resource_type="PushToken",
        resource_id=token_id,
        request=request,
        new_values={"platform": platform},
    )
