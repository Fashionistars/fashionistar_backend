# apps/support/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router

from apps.admin_backend.permissions import admin_auth
from apps.support.admin_backend.selectors import AdminSupportSelector
from apps.support.admin_backend.schemas import AdminSupportTicketSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Support"])

@router.get("/", response=List[AdminSupportTicketSchema], auth=admin_auth)
async def list_tickets(
    request,
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Get all support tickets in the system.
    """
    filters = {"status": status, "category": category, "search": search}
    return await AdminSupportSelector.aget_tickets_list(filters)

@router.get("/{ticket_id}/", response=AdminSupportTicketSchema, auth=admin_auth)
async def get_ticket_detail(request, ticket_id: str):
    """
    Get detailed information and full chat/message log of a specific support ticket.
    """
    try:
        return await AdminSupportSelector.aget_ticket_detail(ticket_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Ticket not found: {str(e)}")
