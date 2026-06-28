# apps/support/apis/async_/support_views.py
"""
Support Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/support/

Architecture:
  ─ Read endpoints → selectors (async, native Django 6.0 ORM).
  ─ All independent DB reads gathered concurrently via asyncio.gather().

IMPORTANT:
  sync_to_async is BANNED. This router is read-only.
  Reference: https://docs.djangoproject.com/en/6.0/topics/async/
"""
import asyncio
import logging
from typing import Optional
from uuid import UUID

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.support.selectors import (
    aget_ticket_or_none,
    aget_user_tickets,
    aget_admin_open_tickets,
    aget_ticket_count,
    aget_ticket_message_thread,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Support — Async"])


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMAS (Pydantic / Ninja)
# ─────────────────────────────────────────────────────────────────────────────

class TicketListItemOut(Schema):
    id:          str
    category:    str
    priority:    str
    status:      str
    title:       str
    order_id:    Optional[str] = None
    created_at:  str

    @classmethod
    def from_ticket(cls, ticket) -> "TicketListItemOut":
        return cls(
            id=str(ticket.id),
            category=ticket.category,
            priority=ticket.priority,
            status=ticket.status,
            title=ticket.title,
            order_id=str(ticket.order_id) if ticket.order_id else None,
            created_at=ticket.created_at.isoformat(),
        )


class TicketFeedOut(Schema):
    total:   int
    tickets: list[TicketListItemOut]


class MessageOut(Schema):
    id:            str
    body:          str
    is_staff_reply: bool
    created_at:   str

    @classmethod
    def from_message(cls, msg) -> "MessageOut":
        return cls(
            id=str(msg.id),
            body=msg.body,
            is_staff_reply=msg.is_staff_reply,
            created_at=msg.created_at.isoformat(),
        )


class TicketDetailOut(Schema):
    id:          str
    category:    str
    priority:    str
    status:      str
    title:       str
    description: str
    order_id:    Optional[str] = None
    resolution_notes: str
    resolved_at: Optional[str] = None
    messages:    list[MessageOut]
    created_at:  str


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tickets/", response=TicketFeedOut)
async def list_tickets(
    request,
    status: Optional[str] = None,
):
    """
    GET /api/v1/ninja/support/tickets/

    Async ticket feed for the authenticated user.
    Concurrently fetches ticket list and total count via asyncio.gather().
    """
    user = request.auth
    try:
        tickets, count = await asyncio.gather(
            aget_user_tickets(user, status=status, limit=50),
            aget_ticket_count(user, status=status),
        )
    except Exception:
        logger.exception("list_tickets: error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Failed to fetch tickets.")

    return TicketFeedOut(
        total=count,
        tickets=[TicketListItemOut.from_ticket(t) for t in tickets],
    )


@router.get("/tickets/{ticket_id}/", response=TicketDetailOut)
async def get_ticket_detail(request, ticket_id: UUID):
    """
    GET /api/v1/ninja/support/tickets/<ticket_id>/

    Async ticket detail with full message thread.
    Fetches the ticket through ``request.auth.submitted_tickets`` first, then
    reads the message thread from ``ticket.messages`` so messages are never read
    for an unowned ticket.
    """
    user = request.auth
    try:
        ticket = await aget_ticket_or_none(ticket_id=ticket_id, user=user)
    except Exception:
        logger.exception("get_ticket_detail: error ticket=%s user=%s", ticket_id, getattr(user, "pk", "?"))
        raise HttpError(500, "Failed to fetch ticket.")

    if ticket is None:
        raise HttpError(404, "Ticket not found.")

    try:
        messages = await aget_ticket_message_thread(ticket)
    except Exception:
        logger.exception("get_ticket_detail: message error ticket=%s user=%s", ticket_id, getattr(user, "pk", "?"))
        raise HttpError(500, "Failed to fetch ticket messages.")

    return TicketDetailOut(
        id=str(ticket.id),
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        title=ticket.title,
        description=ticket.description,
        order_id=str(ticket.order_id) if ticket.order_id else None,
        resolution_notes=ticket.resolution_notes,
        resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        messages=[MessageOut.from_message(m) for m in messages],
        created_at=ticket.created_at.isoformat(),
    )


@router.get("/admin/queue/", response=TicketFeedOut)
async def admin_ticket_queue(
    request,
    status: Optional[str] = None,
    priority: Optional[str] = None,
):
    """
    GET /api/v1/ninja/support/admin/queue/

    Staff-only: async all-user ticket queue.
    Guarded by is_staff check — returns 403 for non-staff callers.
    """
    user = request.auth
    if not getattr(user, "is_staff", False):
        raise HttpError(403, "Staff access required.")

    try:
        tickets = await aget_admin_open_tickets(
            status=status,
            priority=priority,
            limit=100,
        )
    except Exception:
        logger.exception("admin_ticket_queue: error for staff=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Failed to fetch admin queue.")

    return TicketFeedOut(
        total=len(tickets),
        tickets=[TicketListItemOut.from_ticket(t) for t in tickets],
    )


# ─────────────────────────────────────────────────────────────────────────────
# SLA Status Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class SLAOut(Schema):
    ticket_id:               str
    priority:                str
    breach_status:           str
    response_breach:         bool
    resolution_breach:       bool
    minutes_to_response:     float
    minutes_to_resolution:   float
    elapsed_pct:             float
    first_response_deadline: Optional[str] = None
    resolution_deadline:     Optional[str] = None
    first_response_at:       Optional[str] = None


class SLADashboardOut(Schema):
    tickets: list[SLAOut]
    metrics: dict


@router.get("/sla/", response=SLADashboardOut)
async def get_sla_dashboard(request):
    """
    GET /api/v1/ninja/support/sla/

    Real-time SLA health dashboard.
    - Non-staff: shows SLA status for own tickets only.
    - Staff: shows SLA status for ALL non-closed system-wide tickets.

    SLA computation is pure Python (no extra DB I/O in the SLA layer).
    """
    from apps.support.services.sla_service import SLAService

    user = request.auth
    try:
        if getattr(user, "is_staff", False):
            tickets = await aget_admin_open_tickets(limit=200)
        else:
            tickets = await aget_user_tickets(user, limit=100)
    except Exception:
        logger.exception(
            "get_sla_dashboard: fetch error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Failed to fetch tickets for SLA computation.")

    statuses = SLAService.evaluate_batch(tickets)
    metrics  = SLAService.compute_metrics(tickets)

    return SLADashboardOut(
        tickets=[SLAOut(**SLAService.serialize_sla(s)) for s in statuses],
        metrics=metrics,
    )
