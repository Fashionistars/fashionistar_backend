# apps/support/admin_backend/services.py
from __future__ import annotations
import logging
from django.db import transaction
from django.utils import timezone
from apps.common.events import event_bus
from apps.support.models.support_ticket import SupportTicket, TicketStatus, TicketEscalation, EscalationStatus

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_assign_ticket(
    ticket_id: str,
    admin_user,
    assignee_user,
) -> SupportTicket:
    """
    Assign a support ticket to a staff member.
    """
    ticket = SupportTicket.objects.select_for_update().get(id=ticket_id)
    ticket.assigned_to = assignee_user
    ticket.status = TicketStatus.IN_REVIEW
    ticket.save()
    
    logger.info("Admin %s assigned ticket %s to %s", admin_user.email, ticket_id, assignee_user.email)
    event_bus.emit_on_commit(
        "admin.support.ticket_assigned",
        ticket_id=str(ticket.id),
        assignee_id=str(assignee_user.id),
        admin_id=str(admin_user.id),
    )
    return ticket

@transaction.atomic
def admin_resolve_ticket(
    ticket_id: str,
    admin_user,
    notes: str,
) -> SupportTicket:
    """
    Mark a support ticket as resolved.
    """
    ticket = SupportTicket.objects.select_for_update().get(id=ticket_id)
    ticket.transition(new_status=TicketStatus.RESOLVED, notes=notes)
    
    logger.info("Admin %s resolved ticket %s", admin_user.email, ticket_id)
    event_bus.emit_on_commit(
        "admin.support.ticket_resolved",
        ticket_id=str(ticket.id),
        admin_id=str(admin_user.id),
    )
    return ticket
