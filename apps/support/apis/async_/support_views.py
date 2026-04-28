# apps/support/apis/async_/support_views.py
"""
Support Domain — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/support/

Architecture:
  ─ Read endpoints → selectors (async, native Django 6.0 ORM).
  ─ Mutation endpoints → run_in_executor (SupportService is sync atomic).
  ─ All independent DB reads gathered concurrently via asyncio.gather().

IMPORTANT:
  sync_to_async is BANNED. Use run_in_executor for atomic service calls.
  Reference: https://docs.djangoproject.com/en/6.0/topics/async/
"""
import asyncio
import functools
import logging
from typing import Optional
from uuid import UUID

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.support.selectors import (
    aget_ticket_or_none,
    aget_user_tickets,
    aget_admin_open_tickets,
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
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _run_sync(func, *args, **kwargs):
    """
    Run a sync function (transaction.atomic service call) in a thread pool.
    NEVER use sync_to_async() — this is the correct Django 6.0 pattern.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


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
            aget_user_tickets(user.id, status=status, limit=50),
            _get_ticket_count(user.id, status=status),
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
    Concurrently fetches ticket + messages via asyncio.gather().
    """
    user = request.auth
    try:
        ticket, messages = await asyncio.gather(
            aget_ticket_or_none(ticket_id=ticket_id, user_id=user.id),
            aget_ticket_message_thread(ticket_id=ticket_id),
        )
    except Exception:
        logger.exception("get_ticket_detail: error ticket=%s user=%s", ticket_id, getattr(user, "pk", "?"))
        raise HttpError(500, "Failed to fetch ticket.")

    if ticket is None:
        raise HttpError(404, "Ticket not found.")

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
# INTERNAL ASYNC HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _get_ticket_count(user_id, *, status: str | None = None) -> int:
    """Thin async wrapper around ORM count for use in gather()."""
    from apps.support.models import SupportTicket
    qs = SupportTicket.objects.filter(submitter_id=user_id)
    if status:
        qs = qs.filter(status=status)
    return await qs.acount()
