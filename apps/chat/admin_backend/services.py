# apps/chat/admin_backend/services.py
from __future__ import annotations
import logging
from django.db import transaction
from django.utils import timezone
from apps.common.events import event_bus
from apps.chat.models.conversation import ChatEscalation, EscalationStatus, ConversationStatus

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_resolve_escalation(
    escalation_id: str,
    admin_user,
    notes: str,
    resolution_status: str,  # 'resolved' or 'dismissed'
) -> ChatEscalation:
    """
    Resolve or dismiss a chat escalation case by admin.
    """
    escalation = ChatEscalation.objects.select_for_update().get(id=escalation_id)
    escalation.status = resolution_status
    escalation.resolution_notes = notes
    escalation.resolved_at = timezone.now()
    escalation.assigned_admin = admin_user
    escalation.save()
    
    conversation = escalation.conversation
    # Revert conversation status back to active or archive it depending on resolution
    if resolution_status == EscalationStatus.RESOLVED:
        conversation.status = ConversationStatus.ACTIVE
    else:
        conversation.status = ConversationStatus.ACTIVE
    conversation.save()
    
    logger.info("Admin %s resolved chat escalation %s as %s", admin_user.email, escalation_id, resolution_status)
    event_bus.emit_on_commit(
        "admin.chat.escalation_resolved",
        escalation_id=str(escalation.id),
        conversation_id=str(conversation.id),
        status=resolution_status,
        admin_id=str(admin_user.id),
    )
    return escalation
