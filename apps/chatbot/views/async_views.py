# apps/chatbot/views/async_views.py
"""
Django Ninja async views for Chatbot domain.
Follows vendor pattern with async endpoints under /api/v1/ninja/chatbot/.
"""

from ninja import Router
from django.http import HttpRequest
from typing import List, Optional
from pydantic import BaseModel
from apps.chatbot.selectors.chatbot_selectors import (
    aget_chatbot_session_or_none,
    aget_chatbot_dashboard_parallel,
    aget_conversation_dashboard_parallel,
)
from apps.chatbot.models import ChatbotSession


router = Router(tags=['Chatbot'])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ChatbotSessionResponse(BaseModel):
    session_id: str
    session_type: str
    status: str
    started_at: str
    last_activity: str


class DashboardResponse(BaseModel):
    session: Optional[ChatbotSessionResponse]
    conversations_count: int
    messages_count: int


# ============================================================================
# Async Endpoints
# ============================================================================

@router.get('/session/', response=Optional[ChatbotSessionResponse])
async def get_chatbot_session(request: HttpRequest):
    """
    Get active chatbot session for authenticated user (async).
    Endpoint: GET /api/v1/ninja/chatbot/session/
    """
    user = request.auth
    if not user:
        return None
    
    session = await aget_chatbot_session_or_none(user)
    if not session:
        return None
    
    return ChatbotSessionResponse(
        session_id=str(session.id),
        session_type=session.session_type,
        status=session.status,
        started_at=session.started_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
    )


@router.get('/dashboard/', response=DashboardResponse)
async def get_chatbot_dashboard(request: HttpRequest):
    """
    Get chatbot dashboard data in parallel (async).
    Endpoint: GET /api/v1/ninja/chatbot/dashboard/
    """
    user = request.auth
    if not user:
        return DashboardResponse(session=None, conversations_count=0, messages_count=0)
    
    dashboard_data = await aget_chatbot_dashboard_parallel(user)
    
    return DashboardResponse(
        session=dashboard_data['session'],
        conversations_count=len(dashboard_data['conversations']),
        messages_count=len(dashboard_data['messages']),
    )


@router.post('/session/start/')
async def start_chatbot_session(request: HttpRequest, session_type: str):
    """
    Start a new chatbot session (async).
    Endpoint: POST /api/v1/ninja/chatbot/session/start/
    """
    from apps.chatbot.models import ChatbotSession
    from apps.audit_logs.services.chatbot import ChatbotAuditService
    
    user = request.auth
    if not user:
        return {'error': 'Authentication required'}
    
    # Check if active session already exists
    existing_session = await aget_chatbot_session_or_none(user)
    if existing_session:
        return {
            'session_id': str(existing_session.id),
            'status': existing_session.status,
            'message': 'Active session already exists',
        }
    
    # Create new session
    session = await ChatbotSession.objects.acreate(
        user=user,
        session_type=session_type,
        status='active',
    )
    
    # Log audit event
    ChatbotAuditService.log_session_started(
        actor=user,
        session_id=str(session.id),
        session_type=session_type,
        request=request,
    )
    
    return {
        'session_id': str(session.id),
        'status': session.status,
        'message': 'Session started successfully',
    }


@router.post('/session/{session_id}/end/')
async def end_chatbot_session(request: HttpRequest, session_id: str):
    """
    End a chatbot session (async).
    Endpoint: POST /api/v1/ninja/chatbot/session/{session_id}/end/
    """
    from apps.audit_logs.services.chatbot import ChatbotAuditService
    
    user = request.auth
    if not user:
        return {'error': 'Authentication required'}
    
    session = await ChatbotSession.objects.aget(id=session_id)
    if session.user != user:
        return {'error': 'Unauthorized'}
    
    await session.aend_session()
    
    # Log audit event
    ChatbotAuditService.log_session_ended(
        actor=user,
        session_id=str(session.id),
        status=session.status,
        request=request,
    )
    
    return {
        'session_id': str(session.id),
        'status': session.status,
        'message': 'Session ended successfully',
    }
