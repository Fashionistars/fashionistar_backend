"""Support domain audit helper — Wave B10."""
from __future__ import annotations


def log_ticket_created(*, actor, ticket_id: str, category: str = "", priority: str = "", request=None) -> None:
    """Record a support ticket creation.

    Args:
        actor: The user creating the ticket.
        ticket_id: SupportTicket PK.
        category: Ticket category string.
        priority: Ticket priority string.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.TICKET_CREATED,
        event_category=EventCategory.SUPPORT,
        action=f"Support ticket created: {ticket_id} category={category} priority={priority}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="SupportTicket",
        resource_id=ticket_id,
        request=request,
        new_values={"category": category, "priority": priority},
        is_compliance=True,
        retention_days=1095,
    )


def log_ticket_escalated(*, actor, ticket_id: str, reason: str = "", request=None) -> None:
    """Record a ticket escalation.

    Args:
        actor: Staff member escalating.
        ticket_id: SupportTicket PK.
        reason: Escalation reason.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.TICKET_ESCALATED,
        event_category=EventCategory.SUPPORT,
        action=f"Ticket escalated: {ticket_id} reason={reason[:200]}",
        actor=actor,
        actor_role="staff",
        resource_type="SupportTicket",
        resource_id=ticket_id,
        request=request,
        severity="warning",
        new_values={"reason": reason},
        is_compliance=True,
        retention_days=1095,
    )


def log_ticket_resolved(*, actor, ticket_id: str, notes: str = "", request=None) -> None:
    """Record a ticket resolution.

    Args:
        actor: Staff member resolving the ticket.
        ticket_id: SupportTicket PK.
        notes: Resolution notes.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.TICKET_RESOLVED,
        event_category=EventCategory.SUPPORT,
        action=f"Ticket resolved: {ticket_id}",
        actor=actor,
        actor_role="staff",
        resource_type="SupportTicket",
        resource_id=ticket_id,
        request=request,
        new_values={"resolution_notes": notes[:500]},
        is_compliance=True,
        retention_days=1095,
    )


def log_ticket_message_added(
    *,
    actor,
    ticket_id: str,
    message_id: str,
    is_staff_reply: bool,
    request=None,
) -> None:
    """Record a message being appended to a support ticket thread.

    Args:
        actor: The user or staff authoring the message.
        ticket_id: SupportTicket PK.
        message_id: TicketMessage PK.
        is_staff_reply: Whether the message came from staff.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.TICKET_CREATED,
        event_category=EventCategory.SUPPORT,
        action=f"Ticket message added: ticket={ticket_id} role={'staff' if is_staff_reply else 'client'}",
        actor=actor,
        actor_role="staff" if is_staff_reply else getattr(actor, "user_type", None),
        resource_type="TicketMessage",
        resource_id=message_id,
        request=request,
        new_values={"ticket_id": ticket_id, "is_staff_reply": is_staff_reply},
        is_compliance=True,
        retention_days=1095,
    )


def log_sla_breach(*, ticket_id: str, sla_hours: int, elapsed_hours: int) -> None:
    """Record an SLA breach on a support ticket.

    Args:
        ticket_id: SupportTicket PK.
        sla_hours: SLA target in hours.
        elapsed_hours: Actual elapsed hours.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.SLA_BREACH,
        event_category=EventCategory.SUPPORT,
        action=f"SLA breach on ticket={ticket_id}: {elapsed_hours}h elapsed (SLA: {sla_hours}h)",
        resource_type="SupportTicket",
        resource_id=ticket_id,
        severity="critical",
        new_values={"sla_hours": sla_hours, "elapsed_hours": elapsed_hours},
        is_compliance=True,
        retention_days=1095,
    )
