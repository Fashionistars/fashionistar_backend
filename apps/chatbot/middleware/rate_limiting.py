"""
Rate Limiting and Security Middleware for Chatbot.
"""

import logging
from typing import Optional
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


class ChatbotRateLimitMiddleware(MiddlewareMixin):
    """
    Middleware to limit the rate of API calls made to the Chatbot service.
    """
    
    DEFAULT_LIMITS = {
        'chatbot_message': {
            'requests': 30,
            'window': 60,
            'description': 'Send Chatbot Message'
        },
        'chatbot_session': {
            'requests': 5,
            'window': 300,
            'description': 'Start Chatbot Session'
        },
        'catalog_support': {
            'requests': 10,
            'window': 600,
            'description': 'Catalog Support Analysis'
        },
        'product_info': {
            'requests': 20,
            'window': 300,
            'description': 'Product Information Search'
        }
    }
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        if not self._is_chatbot_api(request.path):
            return None
        
        if not request.user.is_authenticated:
            return self._handle_anonymous_rate_limit(request)
        
        return self._handle_authenticated_rate_limit(request)
    
    def _is_chatbot_api(self, path: str) -> bool:
        return '/chatbot/api/' in path or '/api/chatbot/' in path
    
    def _handle_anonymous_rate_limit(self, request):
        ip = self._get_client_ip(request)
        cache_key = f"rate_limit:ip:{ip}"
        
        limit_config = {
            'requests': 10,
            'window': 300,
            'description': 'Unauthenticated Request'
        }
        
        return self._check_rate_limit(cache_key, limit_config)
    
    def _handle_authenticated_rate_limit(self, request):
        endpoint_type = self._get_endpoint_type(request.path)
        if not endpoint_type:
            return None
        
        limit_config = self.DEFAULT_LIMITS.get(endpoint_type)
        if not limit_config:
            return None
        
        cache_key = f"rate_limit:user:{request.user.id}:{endpoint_type}"
        return self._check_rate_limit(cache_key, limit_config)
    
    def _get_endpoint_type(self, path: str) -> Optional[str]:
        if 'send-message' in path:
            return 'chatbot_message'
        elif 'start-session' in path:
            return 'chatbot_session'
        elif 'catalog-support' in path:
            return 'catalog_support'
        elif 'product-info' in path:
            return 'product_info'
        return None
    
    def _check_rate_limit(self, cache_key: str, limit_config: dict):
        now = int(timezone.now().timestamp())
        window = limit_config['window']
        max_requests = limit_config['requests']
        
        requests_history = cache.get(cache_key) or []
        requests_history = [t for t in requests_history if now - t < window]
        
        if len(requests_history) >= max_requests:
            retry_after = window - (now - requests_history[0])
            logger.warning(f"Rate limit exceeded for key: {cache_key}. Retry after {retry_after} seconds.")
            return JsonResponse({
                'error': 'Rate limit exceeded.',
                'retry_after': int(retry_after),
                'description': limit_config['description']
            }, status=429)
        
        requests_history.append(now)
        cache.set(cache_key, requests_history, timeout=window)
        return None
    
    def _get_client_ip(self, request) -> str:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip or 'unknown'


class ChatbotSecurityMiddleware(MiddlewareMixin):
    """
    Security middleware for filtering sensitive keywords.
    """
    
    SENSITIVE_KEYWORDS = [
        'password',
        'social security',
        'credit card',
        'bank account'
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        if not self._is_chatbot_api(request.path):
            return None
        
        if request.method == 'POST' and hasattr(request, 'body'):
            try:
                body_content = request.body.decode('utf-8').lower()
                if self._contains_sensitive_content(body_content):
                    user_identifier = request.user.id if request.user.is_authenticated else 'anonymous'
                    logger.warning(f"Sensitive content detected in request from user {user_identifier}.")
                    return JsonResponse({
                        'error': 'Sensitive content detected.',
                        'code': 'SENSITIVE_CONTENT_DETECTED'
                    }, status=400)
            except Exception:
                pass
        return None
    
    def _is_chatbot_api(self, path: str) -> bool:
        return '/chatbot/api/' in path or '/api/chatbot/' in path
    
    def _contains_sensitive_content(self, content: str) -> bool:
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword in content:
                return True
        return False