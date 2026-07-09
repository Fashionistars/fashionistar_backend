# apps/chatbot/selectors/chatbot_selectors.py
"""
Read-only data fetching layer for Chatbot domain.
Follows vendor pattern with sync and async dual methods.
"""

import asyncio
from typing import Optional, List
from apps.chatbot.models import ChatbotSession, Conversation, Message


# ============================================================================
# SYNC SELECTORS (for DRF)
# ============================================================================

def get_chatbot_session_or_none(user) -> Optional[ChatbotSession]:
    """Get active chatbot session for a user (sync)."""
    try:
        return ChatbotSession.objects.select_related('user').get(
            user=user, status='active'
        )
    except ChatbotSession.DoesNotExist:
        return None


def get_chatbot_sessions(user, status: str = None) -> List[ChatbotSession]:
    """Get all chatbot sessions for a user (sync)."""
    queryset = ChatbotSession.objects.filter(user=user)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by('-started_at'))


def get_conversation(session) -> Optional[Conversation]:
    """Get active conversation for a session (sync)."""
    try:
        return session.conversations.filter(is_active=True).first()
    except Conversation.DoesNotExist:
        return None


def get_conversations(session, is_active: bool = None) -> List[Conversation]:
    """Get all conversations for a session (sync)."""
    queryset = session.conversations.all()
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return list(queryset.order_by('-started_at'))


def get_messages(conversation, limit: int = 10) -> List[Message]:
    """Get recent messages for a conversation (sync)."""
    return list(conversation.messages.order_by('-created_at')[:limit])


def get_message_count(conversation) -> int:
    """Get total message count for a conversation (sync)."""
    return conversation.messages.count()


def get_last_message(conversation) -> Optional[Message]:
    """Get last message in a conversation (sync)."""
    return conversation.messages.order_by('-created_at').first()


def get_chatbot_response(category: str, target_user: str = 'both') -> List:
    """Get active chatbot responses by category (sync)."""
    from apps.chatbot.models import ChatbotResponse
    return list(
        ChatbotResponse.objects.filter(
            category=category,
            target_user=target_user,
            is_active=True
        ).order_by('-priority', '-created_at')
    )


# ============================================================================
# ASYNC SELECTORS (for Django Ninja)
# ============================================================================

async def aget_chatbot_session_or_none(user) -> Optional[ChatbotSession]:
    """Get active chatbot session for a user (async)."""
    try:
        return await ChatbotSession.objects.select_related('user').aget(
            user=user, status='active'
        )
    except ChatbotSession.DoesNotExist:
        return None


async def aget_chatbot_sessions(user, status: str = None) -> List[ChatbotSession]:
    """Get all chatbot sessions for a user (async)."""
    queryset = ChatbotSession.objects.filter(user=user)
    if status:
        queryset = queryset.filter(status=status)
    return [s async for s in queryset.order_by('-started_at')]


async def aget_conversation(session) -> Optional[Conversation]:
    """Get active conversation for a session (async)."""
    try:
        return await session.conversations.filter(is_active=True).afirst()
    except Conversation.DoesNotExist:
        return None


async def aget_conversations(session, is_active: bool = None) -> List[Conversation]:
    """Get all conversations for a session (async)."""
    queryset = session.conversations.all()
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return [c async for c in queryset.order_by('-started_at')]


async def aget_messages(conversation, limit: int = 10) -> List[Message]:
    """Get recent messages for a conversation (async)."""
    return [m async for m in conversation.messages.order_by('-created_at')[:limit]]


async def aget_message_count(conversation) -> int:
    """Get total message count for a conversation (async)."""
    return await conversation.messages.acount()


async def aget_last_message(conversation) -> Optional[Message]:
    """Get last message in a conversation (async)."""
    return await conversation.messages.order_by('-created_at').afirst()


async def aget_chatbot_response(category: str, target_user: str = 'both') -> List:
    """Get active chatbot responses by category (async)."""
    from apps.chatbot.models import ChatbotResponse
    queryset = ChatbotResponse.objects.filter(
        category=category,
        target_user=target_user,
        is_active=True
    ).order_by('-priority', '-created_at')
    return [r async for r in queryset]


# ============================================================================
# PARALLEL LOADING (async only)
# ============================================================================

async def aget_chatbot_dashboard_parallel(user) -> dict:
    """
    Load chatbot dashboard data in parallel using asyncio.gather.
    Returns session, conversations, and recent messages.
    """
    session = await aget_chatbot_session_or_none(user)
    
    if not session:
        return {
            'session': None,
            'conversations': [],
            'messages': [],
        }
    
    # Load conversations and messages in parallel
    conversations, messages = await asyncio.gather(
        aget_conversations(session, is_active=True),
        aget_messages(session.conversations.filter(is_active=True).first(), 10) if session.conversations.filter(is_active=True).exists() else [],
        return_exceptions=True,
    )
    
    return {
        'session': session,
        'conversations': conversations if not isinstance(conversations, Exception) else [],
        'messages': messages if not isinstance(messages, Exception) else [],
    }


async def aget_conversation_dashboard_parallel(conversation_id) -> dict:
    """
    Load conversation dashboard data in parallel.
    Returns conversation, message count, and recent messages.
    """
    from apps.chatbot.models import Conversation
    
    conversation = await Conversation.objects.select_related('session__user').aget(id=conversation_id)
    
    message_count, last_message, recent_messages = await asyncio.gather(
        aget_message_count(conversation),
        aget_last_message(conversation),
        aget_messages(conversation, 10),
        return_exceptions=True,
    )
    
    return {
        'conversation': conversation,
        'message_count': message_count if not isinstance(message_count, Exception) else 0,
        'last_message': last_message if not isinstance(last_message, Exception) else None,
        'recent_messages': recent_messages if not isinstance(recent_messages, Exception) else [],
    }
