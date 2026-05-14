"""Chat & Messaging domain audit helper — Wave B11."""
from __future__ import annotations


def log_conversation_started(
    *, actor, conversation_id: str, participants: list | None = None, request=None
) -> None:
    """Record a new conversation being started.

    Args:
        actor: The user initiating the conversation.
        conversation_id: Conversation PK.
        participants: List of participant user PKs (string).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CONVERSATION_STARTED,
        event_category=EventCategory.CHAT,
        action=f"Conversation started: id={conversation_id} participants={len(participants or [])}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Conversation",
        resource_id=conversation_id,
        request=request,
        new_values={"participants": participants or []},
    )


def log_message_sent(
    *, actor, conversation_id: str, message_id: str,
    message_type: str = "text", request=None
) -> None:
    """Record a chat message sent.

    Args:
        actor: The user sending the message.
        conversation_id: Conversation PK.
        message_id: Message PK.
        message_type: Message content type (text, image, file).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MESSAGE_SENT,
        event_category=EventCategory.CHAT,
        action=f"Message sent: conv={conversation_id} type={message_type}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Message",
        resource_id=message_id,
        request=request,
        new_values={"conversation_id": conversation_id, "type": message_type},
    )


def log_offer_created(
    *,
    actor,
    conversation_id: str,
    offer_id: str,
    offered_price: str,
    quantity: int,
    request=None,
) -> None:
    """Record a structured chat offer event using the chat helper namespace."""
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MESSAGE_SENT,
        event_category=EventCategory.CHAT,
        action=f"Offer created: offer={offer_id} conv={conversation_id} price={offered_price}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="ChatOffer",
        resource_id=offer_id,
        request=request,
        new_values={
            "conversation_id": conversation_id,
            "offered_price": offered_price,
            "quantity": quantity,
            "type": "offer",
        },
        is_compliance=True,
        retention_days=-1,
    )


def log_message_deleted(
    *, actor, message_id: str, conversation_id: str, request=None
) -> None:
    """Record a chat message deletion (soft-delete / recall).

    Args:
        actor: The user or admin deleting the message.
        message_id: Message PK.
        conversation_id: Parent Conversation PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.MESSAGE_DELETED,
        event_category=EventCategory.CHAT,
        action=f"Message deleted: msg={message_id} from conv={conversation_id}",
        actor=actor,
        resource_type="Message",
        resource_id=message_id,
        request=request,
        severity="warning",
        old_values={"conversation_id": conversation_id},
    )


def log_websocket_connected(*, actor, conversation_id: str, session_id: str | None = None) -> None:
    """Record a WebSocket connection established for a chat room.

    Args:
        actor: The connected user.
        conversation_id: Room / Conversation PK.
        session_id: JWT jti used to authenticate the WS.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WEBSOCKET_CONNECTED,
        event_category=EventCategory.CHAT,
        action=f"WebSocket connected: user={getattr(actor, 'email', str(actor))} conv={conversation_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Conversation",
        resource_id=conversation_id,
        session_id=session_id,
    )


def log_websocket_disconnected(
    *, actor, conversation_id: str, reason: str = "", session_id: str | None = None
) -> None:
    """Record a WebSocket disconnection.

    Args:
        actor: The disconnected user.
        conversation_id: Room / Conversation PK.
        reason: Close reason code / string.
        session_id: JWT jti.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WEBSOCKET_DISCONNECTED,
        event_category=EventCategory.CHAT,
        action=f"WebSocket disconnected: user={getattr(actor, 'email', str(actor))} reason={reason}",
        actor=actor,
        resource_type="Conversation",
        resource_id=conversation_id,
        session_id=session_id,
        new_values={"reason": reason},
    )


def log_conversation_flagged(
    *,
    actor,
    conversation_id: str,
    flag_id: str,
    reason: str,
    details: str = "",
    request=None,
) -> None:
    """Record moderation escalation or flagging for a conversation."""
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.CHAT_MESSAGE_FLAGGED,
        event_category=EventCategory.CHAT,
        action=f"Conversation flagged: conv={conversation_id} reason={reason}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="ModerationFlag",
        resource_id=flag_id,
        request=request,
        severity="warning",
        new_values={"conversation_id": conversation_id, "reason": reason, "details": details},
    )
