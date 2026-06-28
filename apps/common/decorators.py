# apps/common/decorators.py
"""
Fashionistar — Common Ingress & Rate Limiting Decorators.
"""
from functools import wraps
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status

def with_api_ingress(rate_limit: int, rate_window: int):
    """
    Standard API ingress decorator providing sliding-window rate limiting.
    Uses the Django Cache (Redis in production, LocMem in dev/test) to track requests.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            user_id = request.user.id if request.user and request.user.is_authenticated else 'anonymous'
            # Get leftmost IP address safely (handling proxy headers)
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '127.0.0.1')
            
            key = f"rate_limit:{user_id}:{ip}:{view_func.__name__}"
            requests_count = cache.get(key, 0)
            
            if requests_count >= rate_limit:
                return Response(
                    {
                        "success": False,
                        "message": "Rate limit exceeded. Please try again later.",
                        "code": "rate_limit_exceeded"
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            
            cache.set(key, requests_count + 1, rate_window)
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator
