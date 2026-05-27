# apps/chat/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router

from apps.admin_backend.permissions import admin_auth
from apps.chat.admin_backend.selectors import AdminChatSelector
from apps.chat.admin_backend.schemas import AdminConversationSchema, AdminChatEscalationSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Chat"])

@router.get("/conversations/", response=List[AdminConversationSchema], auth=admin_auth)
async def list_conversations(
    request,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Get all conversation logs between buyers and vendors.
    """
    filters = {"status": status, "search": search}
    return await AdminChatSelector.get_conversations_queryset(filters)

@router.get("/conversations/{conversation_id}/", response=AdminConversationSchema, auth=admin_auth)
async def get_conversation_detail(request, conversation_id: str):
    """
    Get deep history and specific details of a conversation.
    """
    try:
        return await AdminChatSelector.aget_conversation_detail(conversation_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Conversation not found: {str(e)}")

@router.get("/escalations/", response=List[AdminChatEscalationSchema], auth=admin_auth)
async def list_escalations(request):
    """
    Get all chat escalation logs requested by users or flagged by the system.
    """
    return await AdminChatSelector.aget_escalations_list()
