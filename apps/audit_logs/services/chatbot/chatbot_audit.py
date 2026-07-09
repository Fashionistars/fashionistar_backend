# apps/audit_logs/services/chatbot/chatbot_audit.py
"""
Audit logging helpers for Chatbot domain.
Follows vendor pattern with thin wrappers delegating to AuditService.
"""

from apps.audit_logs.services import AuditService
from apps.audit_logs.models import EventType, EventCategory


class ChatbotAuditService:
    """Audit service for Chatbot domain events."""
    
    @staticmethod
    def log_message_sent(actor, message_id, conversation_id, session_id, request=None):
        """Log when a chatbot message is sent."""
        AuditService.log(
            event_type=EventType.CHATBOT_MESSAGE_SENT,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot message sent",
            request=request,
            details={
                'message_id': str(message_id),
                'conversation_id': str(conversation_id),
                'session_id': str(session_id),
            },
        )
    
    @staticmethod
    def log_session_started(actor, session_id, session_type, request=None):
        """Log when a chatbot session is started."""
        AuditService.log(
            event_type=EventType.CHATBOT_SESSION_STARTED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot session started",
            request=request,
            details={
                'session_id': str(session_id),
                'session_type': session_type,
            },
        )
    
    @staticmethod
    def log_session_ended(actor, session_id, status, request=None):
        """Log when a chatbot session is ended."""
        AuditService.log(
            event_type=EventType.CHATBOT_SESSION_ENDED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot session ended",
            request=request,
            details={
                'session_id': str(session_id),
                'status': status,
            },
        )
    
    @staticmethod
    def log_conversation_created(actor, conversation_id, conversation_type, session_id, request=None):
        """Log when a chatbot conversation is created."""
        AuditService.log(
            event_type=EventType.CHATBOT_CONVERSATION_CREATED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot conversation created",
            request=request,
            details={
                'conversation_id': str(conversation_id),
                'conversation_type': conversation_type,
                'session_id': str(session_id),
            },
        )
    
    @staticmethod
    def log_conversation_updated(actor, conversation_id, update_type, request=None):
        """Log when a chatbot conversation is updated."""
        AuditService.log(
            event_type=EventType.CHATBOT_CONVERSATION_UPDATED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot conversation updated",
            request=request,
            details={
                'conversation_id': str(conversation_id),
                'update_type': update_type,
            },
        )
    
    @staticmethod
    def log_response_triggered(actor, response_id, category, trigger_keyword, request=None):
        """Log when a predefined chatbot response is triggered."""
        AuditService.log(
            event_type=EventType.CHATBOT_RESPONSE_TRIGGERED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot predefined response triggered",
            request=request,
            details={
                'response_id': str(response_id),
                'category': category,
                'trigger_keyword': trigger_keyword,
            },
        )
    
    @staticmethod
    def log_ai_response_generated(actor, conversation_id, confidence_score, processing_time, request=None):
        """Log when an AI response is generated."""
        AuditService.log(
            event_type=EventType.CHATBOT_AI_RESPONSE_GENERATED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Chatbot AI response generated",
            request=request,
            details={
                'conversation_id': str(conversation_id),
                'confidence_score': confidence_score,
                'processing_time': processing_time,
            },
        )
    
    @staticmethod
    def log_style_assessment_started(actor, conversation_id, request=None):
        """Log when a style assessment flow is started."""
        AuditService.log(
            event_type=EventType.CHATBOT_STYLE_ASSESSMENT_STARTED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Style assessment flow started",
            request=request,
            details={
                'conversation_id': str(conversation_id),
            },
        )
    
    @staticmethod
    def log_style_assessment_completed(actor, conversation_id, preferred_style, urgency_level, request=None):
        """Log when a style assessment is completed."""
        AuditService.log(
            event_type=EventType.CHATBOT_STYLE_ASSESSMENT_COMPLETED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Style assessment completed",
            request=request,
            details={
                'conversation_id': str(conversation_id),
                'preferred_style': preferred_style,
                'urgency_level': urgency_level,
            },
        )
    
    @staticmethod
    def log_appointment_requested(actor, conversation_id, specialty, preferred_time, request=None):
        """Log when a bespoke tailoring appointment is requested."""
        AuditService.log(
            event_type=EventType.CHATBOT_APPOINTMENT_REQUESTED,
            event_category=EventCategory.CHATBOT,
            actor=actor,
            action="Bespoke tailoring appointment requested",
            request=request,
            details={
                'conversation_id': str(conversation_id),
                'specialty': specialty,
                'preferred_time': preferred_time,
            },
        )
