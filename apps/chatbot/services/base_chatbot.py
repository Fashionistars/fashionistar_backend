"""
Base Chatbot Service for Fashionistar.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.contrib.auth import get_user_model
from ..models import ChatbotSession, Conversation, Message, ChatbotResponse

User = get_user_model()


class BaseChatbotService(ABC):
    """
    Abstract base service for chatbot engines.
    """
    
    def __init__(self, user: User, session_type: str):
        self.user = user
        self.session_type = session_type
        self.current_session: Optional[ChatbotSession] = None
        self.current_conversation: Optional[Conversation] = None
    
    def get_or_create_session(self) -> ChatbotSession:
        """
        Get an active chatbot session or create a new one.
        """
        active_session = ChatbotSession.objects.filter(
            user=self.user,
            session_type=self.session_type,
            status='active'
        ).first()
        
        if active_session and active_session.is_session_active:
            self.current_session = active_session
        else:
            self.current_session = ChatbotSession.objects.create(
                user=self.user,
                session_type=self.session_type,
                status='active',
                expires_at=timezone.now() + timezone.timedelta(hours=24)
            )
        
        return self.current_session
    
    def get_or_create_conversation(self, conversation_type: str = 'general') -> Conversation:
        """
        Get active conversation or create one.
        """
        if not self.current_session:
            self.get_or_create_session()
        
        active_conversation = self.current_session.conversations.filter(
            is_active=True
        ).first()
        
        if active_conversation:
            self.current_conversation = active_conversation
        else:
            self.current_conversation = Conversation.objects.create(
                session=self.current_session,
                conversation_type=conversation_type,
                title=self._generate_conversation_title(conversation_type)
            )
        
        return self.current_conversation
    
    def save_user_message(self, content: str, message_type: str = 'text') -> Message:
        """
        Save user message in the current conversation.
        """
        if not self.current_conversation:
            self.get_or_create_conversation()
        
        return Message.objects.create(
            conversation=self.current_conversation,
            sender_type='user',
            message_type=message_type,
            content=content
        )
    
    def save_bot_message(
        self, 
        content: str, 
        message_type: str = 'text',
        response_data: Optional[Dict] = None,
        ai_confidence: Optional[float] = None,
        processing_time: Optional[float] = None
    ) -> Message:
        """
        Save bot response message.
        """
        if not self.current_conversation:
            self.get_or_create_conversation()
        
        return Message.objects.create(
            conversation=self.current_conversation,
            sender_type='bot',
            message_type=message_type,
            content=content,
            response_data=response_data or {},
            ai_confidence=ai_confidence,
            processing_time=processing_time
        )
    
    def get_conversation_history(self, limit: int = 50) -> List[Message]:
        """
        Retrieve messages in the current conversation.
        """
        if not self.current_conversation:
            return []
        
        return list(
            self.current_conversation.messages.order_by('-created_at')[:limit]
        )
    
    def end_conversation(self, summary: str = "") -> None:
        """
        Set the active conversation to inactive.
        """
        if self.current_conversation:
            self.current_conversation.is_active = False
            if summary:
                self.current_conversation.summary = summary
            self.current_conversation.save()
    
    def end_session(self) -> None:
        """
        Mark session as completed.
        """
        if self.current_session:
            self.current_session.end_session()
    
    @abstractmethod
    def process_message(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process a user message and return structured bot response.
        """
        pass
    
    @abstractmethod
    def get_quick_replies(self, context: Optional[Dict] = None) -> List[Dict]:
        """
        Get quick reply options.
        """
        pass
    
    def _generate_conversation_title(self, conversation_type: str) -> str:
        """
        Generate localized/human-readable title based on type.
        """
        type_titles = {
            'style_advice': 'Style Advice',
            'size_recommendation': 'Size Recommendation',
            'product_search': 'Product Search',
            'order_inquiry': 'Order Inquiry',
            'general_support': 'General Support',
            'general': 'General Conversation'
        }
        
        base_title = type_titles.get(conversation_type, 'Conversation')
        timestamp = timezone.now().strftime('%H:%M')
        return f"{base_title} - {timestamp}"
    
    def _update_session_context(self, context_updates: Dict) -> None:
        if self.current_session:
            self.current_session.context_data.update(context_updates)
            self.current_session.save(update_fields=['context_data', 'last_activity'])