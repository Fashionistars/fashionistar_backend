"""
Response Matcher Service for Chatbot.
"""

import re
from typing import List, Optional, Dict, Any
from django.db.models import Q
from ..models import ChatbotResponse


class ResponseMatcherService:
    """
    Service to match user messages against predefined chatbot responses.
    """
    
    def __init__(self, target_user: str = 'both'):
        self.target_user = target_user
    
    def find_matching_response(
        self, 
        message: str, 
        category: Optional[str] = None
    ) -> Optional[ChatbotResponse]:
        """
        Finds the first active ChatbotResponse matching the user message.
        """
        queryset = ChatbotResponse.objects.filter(
            is_active=True
        ).filter(
            Q(target_user=self.target_user) | Q(target_user='both')
        )
        
        if category:
            queryset = queryset.filter(category=category)
        
        responses = queryset.order_by('-priority', '-created_at')
        message_lower = message.lower().strip()
        
        for response in responses:
            if self._matches_keywords(message_lower, response.trigger_keywords):
                return response
        
        return None
    
    def get_responses_by_category(self, category: str) -> List[ChatbotResponse]:
        """
        Retrieve list of active responses in a category.
        """
        return list(
            ChatbotResponse.objects.filter(
                category=category,
                is_active=True
            ).filter(
                Q(target_user=self.target_user) | Q(target_user='both')
            ).order_by('-priority', '-created_at')
        )
    
    def get_greeting_response(self) -> Optional[ChatbotResponse]:
        responses = self.get_responses_by_category('greeting')
        return responses[0] if responses else None
    
    def get_error_response(self) -> Optional[ChatbotResponse]:
        responses = self.get_responses_by_category('error')
        return responses[0] if responses else None
    
    def get_unknown_response(self) -> Optional[ChatbotResponse]:
        responses = self.get_responses_by_category('unknown')
        return responses[0] if responses else None
    
    def _matches_keywords(self, message: str, keywords: List[str]) -> bool:
        if not keywords:
            return False
        
        for keyword in keywords:
            keyword_lower = keyword.lower().strip()
            if keyword_lower in message:
                return True
            if self._regex_match(keyword_lower, message):
                return True
        
        return False
    
    def _regex_match(self, pattern: str, message: str) -> bool:
        try:
            if any(char in pattern for char in r'.*+?[]{}()|^$\\'):
                return bool(re.search(pattern, message))
            else:
                return bool(re.search(r'\b' + re.escape(pattern) + r'\b', message))
        except re.error:
            return False
    
    def analyze_message_intent(self, message: str) -> Dict[str, Any]:
        """
        Analyze the intent of the message and return matching categories and confidence scores.
        """
        message_lower = message.lower().strip()
        
        intent_keywords = {
            'greeting': ['hello', 'hi', 'hey', 'greetings', 'morning', 'afternoon'],
            'sizing_inquiry': ['size', 'sizing', 'fit', 'measurement', 'chest', 'waist', 'hips', 'inseam', 'large', 'medium', 'small'],
            'styling_recommendation': ['style', 'recommendation', 'advice', 'wear', 'outfit', 'match', 'color', 'suit', 'dress'],
            'order_help': ['order', 'track', 'status', 'shipping', 'delivery', 'receive', 'package'],
            'shipping_returns': ['return', 'refund', 'exchange', 'ship', 'postal', 'courier'],
            'product_info': ['price', 'material', 'fabric', 'cotton', 'silk', 'wool', 'linen', 'cost', 'expensive'],
            'farewell': ['bye', 'goodbye', 'thanks', 'thank you', 'see you']
        }
        
        detected_intents = []
        confidence_scores = {}
        
        for intent, keywords in intent_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in message_lower)
            if matches > 0:
                detected_intents.append(intent)
                confidence_scores[intent] = matches / len(keywords)
        
        primary_intent = None
        if detected_intents:
            primary_intent = max(detected_intents, key=lambda x: confidence_scores[x])
        
        return {
            'primary_intent': primary_intent,
            'detected_intents': detected_intents,
            'confidence_scores': confidence_scores,
            'message_length': len(message),
            'word_count': len(message.split())
        }