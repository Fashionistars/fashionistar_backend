"""
Client Chatbot Service for Fashionistar.
"""

from typing import Dict, List, Optional, Any
from django.utils import timezone
from .base_chatbot import BaseChatbotService
from .ai_integration import AIIntegrationService


class ClientChatbotService(BaseChatbotService):
    """
    Dedicated chatbot service for client users.
    """
    
    def __init__(self, user):
        super().__init__(user, 'client')
        self.ai_service = AIIntegrationService('client')
    
    def process_message(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        user_message = self.save_user_message(message)
        conversation_history = self.get_conversation_history(10)
        
        ai_response = self.ai_service.process_message(
            message=message,
            context=context,
            conversation_history=conversation_history
        )
        
        bot_message = self.save_bot_message(
            content=ai_response['content'],
            message_type=ai_response.get('message_type', 'text'),
            response_data=ai_response.get('response_data', {}),
            ai_confidence=ai_response.get('ai_confidence'),
            processing_time=ai_response.get('processing_time')
        )
        
        self._update_client_context(ai_response, context)
        
        return {
            'response': ai_response,
            'user_message_id': str(user_message.id),
            'bot_message_id': str(bot_message.id),
            'conversation_id': str(self.current_conversation.id),
            'session_id': str(self.current_session.id)
        }
    
    def get_quick_replies(self, context: Optional[Dict] = None) -> List[Dict]:
        base_replies = [
            {'title': 'Sizing Recommendation', 'payload': 'size_recommendation'},
            {'title': 'Style Assessment', 'payload': 'style_assessment'},
            {'title': 'Bespoke Tailoring', 'payload': 'bespoke_tailoring'},
            {'title': 'Contact Support', 'payload': 'contact_support'}
        ]
        
        if context:
            if context.get('has_style_profile'):
                base_replies.extend([
                    {'title': 'Change Style Preference', 'payload': 'change_style'},
                    {'title': 'View Saved Outfits', 'payload': 'view_outfits'}
                ])
            
            if context.get('has_active_order'):
                base_replies.extend([
                    {'title': 'Track My Order', 'payload': 'track_order'},
                    {'title': 'Order Return Info', 'payload': 'order_returns'}
                ])
        
        return base_replies
    
    def start_style_assessment(self) -> Dict[str, Any]:
        """
        Start the style assessment flow for the client.
        """
        if self.current_conversation:
            self.current_conversation.conversation_type = 'style_advice'
            self.current_conversation.save()
        
        return {
            'content': 'To help match your style, please answer these brief questions:',
            'message_type': 'text',
            'response_data': {
                'assessment_questions': [
                    {
                        'id': 'preferred_style',
                        'question': 'What is your preferred aesthetic?',
                        'type': 'multiple_choice',
                        'options': [
                            'Casual',
                            'Classic',
                            'Streetwear',
                            'Elegant',
                            'Vintage',
                            'Other'
                        ]
                    },
                    {
                        'id': 'budget_range',
                        'question': 'What is your preferred budget range per item?',
                        'type': 'multiple_choice',
                        'options': [
                            'Under $50',
                            '$50-$150',
                            '$150-$300',
                            'Above $300'
                        ]
                    },
                    {
                        'id': 'formality_level',
                        'question': 'How formal is this outfit intended to be?',
                        'type': 'scale',
                        'scale': {'min': 1, 'max': 10, 'labels': {'1': 'Very Casual', '10': 'Very Formal'}}
                    }
                ]
            }
        }
    
    def process_style_response(self, responses: Dict) -> Dict[str, Any]:
        """
        Process the client style responses and save to context.
        """
        self._update_session_context({
            'style_assessment': responses,
            'assessment_completed_at': str(timezone.now())
        })
        
        analysis = self._analyze_style_responses(responses)
        
        return {
            'content': analysis['message'],
            'message_type': 'text',
            'response_data': {
                'analysis': analysis,
                'recommendations': analysis.get('recommendations', []),
                'urgency_level': analysis.get('urgency_level', 'normal'),
                'quick_replies': self._get_style_followup_replies(analysis)
            }
        }
    
    def request_appointment(self, specialty: str = None, preferred_time: str = None) -> Dict[str, Any]:
        """
        Request a bespoke tailoring consultation appointment.
        """
        if self.current_conversation:
            self.current_conversation.conversation_type = 'general_support'
            self.current_conversation.save()
        
        self._update_session_context({
            'appointment_request': {
                'specialty': specialty,
                'preferred_time': preferred_time,
                'requested_at': str(timezone.now())
            }
        })
        
        return {
            'content': 'Your bespoke tailoring consultation request was received. Please provide additional preferences:',
            'message_type': 'text',
            'response_data': {
                'appointment_form': {
                    'specialty_options': [
                        'Custom Suits',
                        'Formal Gowns',
                        'Everyday Tailoring',
                        'Alterations',
                        'Bridal Tailoring'
                    ],
                    'time_slots': [
                        'Morning (8 AM - 12 PM)',
                        'Afternoon (12 PM - 4 PM)',
                        'Evening (4 PM - 8 PM)'
                    ]
                },
                'quick_replies': [
                    {'title': 'Confirm Consultation', 'payload': 'confirm_appointment'},
                    {'title': 'Change Time Slot', 'payload': 'change_time'},
                    {'title': 'Cancel Request', 'payload': 'cancel_appointment'}
                ]
            }
        }
    
    def _analyze_style_responses(self, responses: Dict) -> Dict[str, Any]:
        preferred_style = responses.get('preferred_style', 'Casual')
        budget_range = responses.get('budget_range', '')
        severity = int(responses.get('formality_level', 5))
        
        urgency_level = 'normal'
        if severity >= 8:
            urgency_level = 'high'
        elif severity >= 6:
            urgency_level = 'medium'
        
        if urgency_level == 'high':
            message = f'For a highly formal event, we recommend our premium bespoke tailoring service for custom {preferred_style.lower()} wear.'
            recommendations = [
                'Schedule custom tailoring consultation',
                'Select luxury fabrics (wool, silk, premium blends)',
                'Submit precise body measurements'
            ]
        elif urgency_level == 'medium':
            message = f'For a smart-casual setting, we recommend exploring our structured blazers and ready-to-wear {preferred_style.lower()} items.'
            recommendations = [
                'View tailored jackets catalog',
                'Check sizing advisor guidelines',
                'Choose breathable fabrics like organic cotton'
            ]
        else:
            message = f'For a relaxed vibe, we suggest checking our casual styling edits for {preferred_style.lower()} outfits.'
            recommendations = [
                'Browse new casual arrivals',
                'Opt for comfortable fits (oversized, relaxed)',
                'Explore linen and soft knit fabrics'
            ]
        
        return {
            'message': message,
            'urgency_level': urgency_level,
            'recommendations': recommendations,
            'severity_score': severity,
            'preferred_style': preferred_style,
            'duration': budget_range
        }
    
    def _get_style_followup_replies(self, analysis: Dict) -> List[Dict]:
        base_replies = [
            {'title': 'Book Consultation', 'payload': 'book_appointment'},
            {'title': 'More Details', 'payload': 'more_info'}
        ]
        
        if analysis.get('urgency_level') == 'high':
            base_replies.insert(0, {'title': 'Contact Tailoring Specialist', 'payload': 'emergency_contact'})
        
        return base_replies
    
    def _update_client_context(self, ai_response: Dict, context: Optional[Dict]):
        updates = {
            'last_interaction': str(timezone.now()),
            'last_category': ai_response.get('category'),
            'confidence_score': ai_response.get('ai_confidence')
        }
        
        if context:
            updates.update(context)
        
        self._update_session_context(updates)
