"""
AI Integration Service for Chatbot.
"""

import time
import logging
from typing import Dict, List, Optional, Any
from .response_matcher import ResponseMatcherService

logger = logging.getLogger(__name__)


class AIIntegrationService:
    """
    AI Integration Service to handle intent-based chatbot responses.
    """
    
    def __init__(self, user_type: str = 'client'):
        self.user_type = user_type
        self.response_matcher = ResponseMatcherService(target_user=user_type)
    
    def process_message(
        self, 
        message: str, 
        context: Optional[Dict] = None,
        conversation_history: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        Process user message and generate appropriate AI or predefined response.
        """
        start_time = time.time()
        
        try:
            intent_analysis = self.response_matcher.analyze_message_intent(message)
            predefined_response = self.response_matcher.find_matching_response(
                message, 
                category=intent_analysis.get('primary_intent')
            )
            
            if predefined_response:
                response = self._format_predefined_response(predefined_response)
                response['ai_confidence'] = 0.9
            else:
                response = self._generate_ai_response(
                    message, context, conversation_history, intent_analysis
                )
            
            processing_time = time.time() - start_time
            response['processing_time'] = processing_time
            response['intent_analysis'] = intent_analysis
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return self._get_error_response()
    
    def _format_predefined_response(self, response_obj) -> Dict[str, Any]:
        return {
            'content': response_obj.response_text,
            'message_type': 'text',
            'response_data': response_obj.response_data,
            'source': 'predefined',
            'category': response_obj.category,
            'ai_confidence': 0.9
        }
    
    def _generate_ai_response(
        self, 
        message: str,
        context: Optional[Dict],
        conversation_history: Optional[List],
        intent_analysis: Dict
    ) -> Dict[str, Any]:
        if self.user_type == 'client':
            return self._generate_client_response(message, intent_analysis)
        else:
            return self._generate_vendor_response(message, intent_analysis)
    
    def _generate_client_response(self, message: str, intent_analysis: Dict) -> Dict[str, Any]:
        primary_intent = intent_analysis.get('primary_intent')
        
        responses = {
            'sizing_inquiry': {
                'content': 'Please describe your sizing or body measurements. To give the best fit advice, what is your height, waist, and chest/bust measurement?',
                'response_data': {
                    'quick_replies': [
                        {'title': 'Size Recommendation', 'payload': 'size_recommendation'},
                        {'title': 'Fit Guide', 'payload': 'fit_guide'},
                        {'title': 'Custom Measurement', 'payload': 'custom_measurement'}
                    ]
                }
            },
            'styling_recommendation': {
                'content': 'To suggest the perfect outfit, what is the occasion? Is it casual, formal, or streetwear, and do you have any color preferences?',
                'response_data': {
                    'quick_replies': [
                        {'title': 'Casual Outfit Ideas', 'payload': 'casual_ideas'},
                        {'title': 'Formal Style Suggestions', 'payload': 'formal_ideas'},
                        {'title': 'Trend Recommendations', 'payload': 'trend_ideas'}
                    ]
                }
            },
            'order_help': {
                'content': 'To check your order status, please enter your Order ID or SKU code.',
                'response_data': {
                    'quick_replies': [
                        {'title': 'Track My Package', 'payload': 'track_package'},
                        {'title': 'Shipping Times', 'payload': 'shipping_times'}
                    ]
                }
            }
        }
        
        if primary_intent in responses:
            response = responses[primary_intent].copy()
            response['ai_confidence'] = 0.7
        else:
            response = {
                'content': 'Thank you for your message. How can I help you find products, check sizes, or styling suggestions today?',
                'ai_confidence': 0.5,
                'response_data': {
                    'quick_replies': [
                        {'title': 'Sizing Help', 'payload': 'sizing_help'},
                        {'title': 'Style Matching', 'payload': 'styling_help'},
                        {'title': 'Order Help', 'payload': 'order_help'}
                    ]
                }
            }
        
        response.update({
            'message_type': 'text',
            'source': 'ai_generated',
            'category': primary_intent or 'general'
        })
        
        return response
    
    def _generate_vendor_response(self, message: str, intent_analysis: Dict) -> Dict[str, Any]:
        primary_intent = intent_analysis.get('primary_intent')
        
        responses = {
            'sizing_inquiry': {
                'content': 'Based on sizing chart criteria, we recommend checking these parameters for your items:',
                'response_data': {
                    'suggestions': [
                        'Review bust, waist, and hips measurements range',
                        'Validate sleeve and shoulder parameters tolerance',
                        'Ensure standard sizing tags correspond to actual dimensions'
                    ],
                    'quick_replies': [
                        {'title': 'Sizing Chart Template', 'payload': 'sizing_template'},
                        {'title': 'Check Tolerances', 'payload': 'check_tolerances'},
                        {'title': 'Upload Size Chart', 'payload': 'upload_chart'}
                    ]
                }
            },
            'styling_recommendation': {
                'content': 'Fabric selection and tailoring assembly guideline recommendations:',
                'response_data': {
                    'quick_replies': [
                        {'title': 'Assembly Guidelines', 'payload': 'assembly_guidelines'},
                        {'title': 'Fabric Incompatibilities', 'payload': 'fabric_incompatibilities'},
                        {'title': 'Material Quality Audit', 'payload': 'quality_audit'}
                    ]
                }
            }
        }
        
        if primary_intent in responses:
            response = responses[primary_intent].copy()
            response['ai_confidence'] = 0.8
        else:
            response = {
                'content': 'How can I assist you with product catalog uploads, fabric advice, or custom order sizing charts?',
                'ai_confidence': 0.6,
                'response_data': {
                    'quick_replies': [
                        {'title': 'Catalog Help', 'payload': 'catalog_help'},
                        {'title': 'Tailoring Protocols', 'payload': 'tailoring_protocols'},
                        {'title': 'Fabric Guide', 'payload': 'fabric_guide'}
                    ]
                }
            }
        
        response.update({
            'message_type': 'text',
            'source': 'ai_generated',
            'category': primary_intent or 'general'
        })
        
        return response
    
    def _get_error_response(self) -> Dict[str, Any]:
        error_response = self.response_matcher.get_error_response()
        
        if error_response:
            return self._format_predefined_response(error_response)
        
        return {
            'content': 'An error occurred while processing your message. Please try again.',
            'message_type': 'text',
            'source': 'system',
            'category': 'error',
            'ai_confidence': 1.0
        }
    
    def get_quick_replies_for_context(self, context: Optional[Dict] = None) -> List[Dict]:
        if self.user_type == 'client':
            return [
                {'title': 'Sizing Help', 'payload': 'sizing_help'},
                {'title': 'Style Matching', 'payload': 'styling_help'},
                {'title': 'Order Help', 'payload': 'order_help'},
                {'title': 'Support', 'payload': 'support'}
            ]
        else:
            return [
                {'title': 'Catalog Guide', 'payload': 'catalog_guide'},
                {'title': 'Tailoring Guidelines', 'payload': 'tailoring_guidelines'},
                {'title': 'Fabric Specs', 'payload': 'fabric_specs'},
                {'title': 'Trend References', 'payload': 'trend_references'}
            ]