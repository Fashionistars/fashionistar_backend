"""
هسته ورودی API - الگوی استاندارد
API Ingress Core - Standard Pattern
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging
import time
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)


class APIIngressCore:
    """
    هسته مدیریت ورودی API
    مسئول validation، authentication، rate limiting و logging
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def validate_request(self, request_data: Dict[str, Any], 
                        serializer_class) -> Tuple[bool, Any]:
        """
        اعتبارسنجی درخواست با استفاده از Serializer
        
        Args:
            request_data: داده‌های درخواست
            serializer_class: کلاس Serializer برای validation
            
        Returns:
            (is_valid, validated_data or errors)
        """
        serializer = serializer_class(data=request_data)
        if not serializer.is_valid():
            self.logger.warning(f"Validation failed: {serializer.errors}")
            return False, serializer.errors
        return True, serializer.validated_data
    
    def check_rate_limit(self, user_id: int, endpoint: str, 
                        limit: int = 100, window: int = 60) -> bool:
        """
        بررسی محدودیت تعداد درخواست
        
        Args:
            user_id: شناسه کاربر
            endpoint: نام endpoint
            limit: حداکثر تعداد درخواست
            window: بازه زمانی به ثانیه
            
        Returns:
            True if allowed, False if rate limited
        """
        cache_key = f"rate_limit:{user_id}:{endpoint}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= limit:
            self.logger.warning(f"Rate limit exceeded for user {user_id} on {endpoint}")
            return False
        
        cache.set(cache_key, current_count + 1, window)
        return True
    
    def log_request(self, request, response_status: int, 
                   execution_time: float = None):
        """
        ثبت لاگ درخواست و پاسخ
        
        Args:
            request: Django request object
            response_status: HTTP status code
            execution_time: زمان اجرا به ثانیه
        """
        log_data = {
            'method': request.method,
            'path': request.path,
            'user': request.user.id if request.user.is_authenticated else 'anonymous',
            'ip': self.get_client_ip(request),
            'status': response_status,
            'execution_time': execution_time,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        }
        
        if response_status >= 400:
            self.logger.error("API Error", extra=log_data)
        else:
            self.logger.info("API Request", extra=log_data)
    
    def get_client_ip(self, request) -> str:
        """دریافت IP واقعی کاربر"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def build_error_response(self, error_type: str, 
                           details: Any = None) -> Dict[str, Any]:
        """
        ساخت پاسخ خطای استاندارد
        
        Args:
            error_type: نوع خطا
            details: جزئیات اضافی
            
        Returns:
            دیکشنری پاسخ خطا
        """
        error_mapping = {
            'validation': {
                'code': 'VALIDATION_ERROR',
                'message': 'داده‌های ورودی معتبر نیستند'
            },
            'authentication': {
                'code': 'AUTH_ERROR',
                'message': 'احراز هویت ناموفق'
            },
            'permission': {
                'code': 'PERMISSION_DENIED',
                'message': 'دسترسی مجاز نیست'
            },
            'rate_limit': {
                'code': 'RATE_LIMIT_EXCEEDED',
                'message': 'تعداد درخواست‌ها بیش از حد مجاز'
            },
            'not_found': {
                'code': 'NOT_FOUND',
                'message': 'منبع مورد نظر یافت نشد'
            },
            'internal': {
                'code': 'INTERNAL_ERROR',
                'message': 'خطای داخلی سرور'
            }
        }
        
        error_info = error_mapping.get(error_type, error_mapping['internal'])
        response = {
            'error': error_info['code'],
            'message': error_info['message']
        }
        
        if details:
            response['details'] = details
            
        return response


# دکوراتور برای استفاده آسان
def with_api_ingress(rate_limit=100, rate_window=60):
    """
    دکوراتور برای اعمال خودکار API Ingress
    
    Args:
        rate_limit: حداکثر تعداد درخواست
        rate_window: بازه زمانی محدودیت
    """
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            ingress = APIIngressCore()
            start_time = time.time()
            
            try:
                # بررسی rate limit
                if request.user.is_authenticated:
                    if not ingress.check_rate_limit(
                        request.user.id, 
                        request.path,
                        rate_limit,
                        rate_window
                    ):
                        return Response(
                            ingress.build_error_response('rate_limit'),
                            status=status.HTTP_429_TOO_MANY_REQUESTS
                        )
                
                # اجرای تابع اصلی
                response = func(request, *args, **kwargs)
                
                # لاگ کردن
                execution_time = time.time() - start_time
                ingress.log_request(request, response.status_code, execution_time)
                
                return response
                
            except Exception as e:
                execution_time = time.time() - start_time
                ingress.log_request(request, 500, execution_time)
                logger.exception("Unhandled exception in API endpoint")
                return Response(
                    ingress.build_error_response('internal'),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        return wrapper
    return decorator


# مثال استفاده
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@with_api_ingress(rate_limit=50, rate_window=60)
def example_endpoint(request):
    """نمونه endpoint با API Ingress"""
    ingress = APIIngressCore()
    
    # Validation
    from .serializers import ExampleSerializer
    is_valid, data = ingress.validate_request(
        request.data, 
        ExampleSerializer
    )
    
    if not is_valid:
        return Response(
            ingress.build_error_response('validation', data),
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Business logic here
    result = {"message": "Success", "data": data}
    
    return Response(result, status=status.HTTP_200_OK)