# apps/support/selectors/support_selectors.py
"""
Support Domain Selectors — Read-only data fetching layer.

Rules:
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync selectors (no prefix) → used in DRF sync views.
  ─ Async selectors (prefix `a`) → used in Ninja async views.
  ─ ZERO sync_to_async(). All async selectors use Django 6.0 native
    async ORM: aget(), afilter(), acount(), alist().
  ─ All reverse relationship traversals use pre-defined related_names
    (e.g. user.submitted_tickets, ticket.messages, ticket.escalation).
"""

import logging
from typing import Optional
from uuid import UUID

from django.db.models import QuerySet

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  SYNC selectors (DRF / admin / management commands)
# ══════════════════════════════════════════════════════════════════════


def get_ticket_or_none(ticket_id: UUID | str, user_id) -> Optional["SupportTicket"]:  # noqa: F821
    """
    Return a SupportTicket owned by the given user, or None.
    Prefetches message thread for detail views.
    """
    from apps.support.models import SupportTicket
    return (
        SupportTicket.objects
        .filter(id=ticket_id, submitter_id=user_id)
        .select_related("submitter", "assigned_to")
        .prefetch_related("messages__author")
        .first()
    )


def get_user_tickets(
    user_id,
    *,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> QuerySet:
    """
    Return a user's support ticket feed, newest first.
    Supports optional status and category filters.
    """
    from apps.support.models import SupportTicket
    qs = (
        SupportTicket.objects
        .filter(submitter_id=user_id)
        .select_related("assigned_to")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)
    return qs[:limit]


def get_admin_open_tickets(
    *,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 100,
) -> QuerySet:
    """
    Admin-level ticket queue. Returns all tickets (not scoped to a single user).
    Optionally filtered by status and/or priority.
    """
    from apps.support.models import SupportTicket, TicketStatus
    qs = (
        SupportTicket.objects
        .exclude(status__in=[TicketStatus.CLOSED])
        .select_related("submitter", "assigned_to")
        .order_by("priority", "-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    return qs[:limit]


# ══════════════════════════════════════════════════════════════════════
#  ASYNC selectors (Django-Ninja async views)
#  ZERO sync_to_async — pure Django 6.0 native async ORM
# ══════════════════════════════════════════════════════════════════════


async def aget_ticket_or_none(
    ticket_id: UUID | str,
    user_id,
) -> Optional["SupportTicket"]:  # noqa: F821
    """
    Async single ticket fetch scoped to the requesting user.
    Returns None if not found or not owned by user.
    """
    from apps.support.models import SupportTicket
    try:
        return await (
            SupportTicket.objects
            .filter(id=ticket_id, submitter_id=user_id)
            .select_related("submitter", "assigned_to")
            .aget()
        )
    except SupportTicket.DoesNotExist:
        return None


async def aget_user_tickets(
    user_id,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list:
    """
    Async ticket feed for a user, newest first.
    Returns a plain list (consumed by Ninja response schema).
    """
    from apps.support.models import SupportTicket
    qs = (
        SupportTicket.objects
        .filter(submitter_id=user_id)
        .select_related("assigned_to")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return [t async for t in qs[:limit]]


async def aget_admin_open_tickets(
    *,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 100,
) -> list:
    """
    Async admin queue — all open tickets.
    Used by the Ninja admin router (staff-only endpoint).
    """
    from apps.support.models import SupportTicket, TicketStatus
    qs = (
        SupportTicket.objects
        .exclude(status__in=[TicketStatus.CLOSED])
        .select_related("submitter", "assigned_to")
        .order_by("priority", "-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    return [t async for t in qs[:limit]]


async def aget_ticket_message_thread(ticket_id: UUID | str) -> list:
    """
    Async fetch of all messages in a ticket's thread, oldest first.
    Used in detail views to render the full conversation.
    """
    from apps.support.models import TicketMessage
    qs = (
        TicketMessage.objects
        .filter(ticket_id=ticket_id)
        .select_related("author")
        .order_by("created_at")
    )
    return [m async for m in qs]


async def aget_ticket_count(user_id, *, status: str | None = None) -> int:
    """Async count of user tickets, optionally filtered by status."""
    from apps.support.models import SupportTicket
    qs = SupportTicket.objects.filter(submitter_id=user_id)
    if status:
        qs = qs.filter(status=status)
    return await qs.acount()
