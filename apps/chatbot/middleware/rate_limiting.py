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
        """
        یک‌خطی:
        مقداردهی اولیهٔ middleware و ذخیرهٔ callable اصلی پردازش درخواست.
        
        توضیح:
        این سازنده، callable که پردازش کنندهٔ درخواست (get_response) را فراهم می‌کند در نمونه ذخیره می‌کند و مقداردهی اولیهٔ کلاس پایه را انجام می‌دهد تا middleware آمادهٔ استفاده در چرخهٔ درخواست/پاسخ Django شود.
        """
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """
        بررسی و اعمال محدودیت نرخ درخواست برای مسیرهای API چت‌بات.
        
        این متد تنها درخواست‌هایی را که مسیرشان متعلق به API چت‌بات تشخیص داده شود بررسی می‌کند. برای درخواست‌های ناشناس محدودیت مبتنی بر آدرس IP اعمال می‌شود و برای درخواست‌های احراز هویت‌شده محدودیت‌های مرتبط با کاربر و نوع endpoint بررسی می‌شوند. در صورتی که درخواست تحت محدودیت قرار گیرد یک JsonResponse با وضعیت HTTP 429 و جزئیات محدودیت بازگردانده می‌شود، در غیر این صورت None بازگردانده و پردازش ادامه پیدا می‌کند.
        
        Parameters:
            request (django.http.HttpRequest): آبجکت درخواست Django که شامل اطلاعات مسیر، کاربر و بدنه درخواست است.
        
        Returns:
            django.http.HttpResponse or None: در صورت نقض محدودیت نرخ، یک JsonResponse (status=429) با اطلاعات خطا بازمی‌گردد؛ در غیر این صورت None.
        """
        # فقط API های چت‌بات را بررسی کن
        if not self._is_chatbot_api(request.path):
            return None
        
        # اگر کاربر احراز هویت نشده، محدودیت IP اعمال کن
        if not request.user.is_authenticated:
            return self._handle_anonymous_rate_limit(request)
        
        return self._handle_authenticated_rate_limit(request)
    
    def _is_chatbot_api(self, path: str) -> bool:
        return '/chatbot/api/' in path or '/api/chatbot/' in path
    
    def _handle_anonymous_rate_limit(self, request):
        ip = self._get_client_ip(request)
        cache_key = f"rate_limit:ip:{ip}"
        
        # محدودیت سخت‌گیرانه‌تر برای IP های ناشناس
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
        """
        آی‌پی کلاینت را از هدرهای درخواست استخراج می‌کند.
        
        این تابع ابتدا هدر HTTP_X_FORWARDED_FOR را بررسی می‌کند و در صورت وجود از اولین آی‌پی لیست (معمولاً آی‌پی اصلی کلاینت در مقابل پراکسی‌ها) استفاده می‌کند. در غیر این صورت مقدار REMOTE_ADDR را بازمی‌گرداند. مقدار بازگشتی همیشه رشته است و در صورت نبود هرگونه مقدار معتبر، 'unknown' بازگردانده می‌شود.
        """
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
    
    # کلمات حساس که باید فیلتر شوند
    SENSITIVE_KEYWORDS = [
        'password',
        'social security',
        'credit card',
        'bank account'
    ]
    
    def __init__(self, get_response):
        """
        یک‌خطی:
        سازنده‌ی میان‌افزار؛ callable بعدی (next middleware یا view) را ذخیره و مقداردهی اولیهٔ کلاس والد را انجام می‌دهد.
        
        توضیحات:
        این متد get_response را که یک callable است (تابعی که درخواست را به میان‌افزار بعدی یا به view هدایت می‌کند) در نمونه ذخیره می‌کند تا در هنگام پردازش درخواست از آن استفاده شود. سپس سازندهٔ کلاس والد را فراخوانی می‌کند تا هر مقداردهی‌اولیهٔ لازم توسط MiddlewareMixin یا والد انجام شود.
        """
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """
        بررسی محتوای ورودی درخواست‌های API چت‌بات و مسدودسازی پیام‌های حاوی داده‌های حساس.
        
        این متد فقط برای مسیرهای مربوط به API چت‌بات اجرا می‌شود. اگر درخواست از نوع POST باشد و بدنه (body) قابل خواندن به‌عنوان UTF‑8 باشد، متن بدنه را به حروف کوچک تبدیل کرده و در برابر فهرست کلیدواژه‌های حساس بررسی می‌کند. در صورت یافتن محتوای حساس، یک هشدار در لاگ ثبت می‌کند (شناسهٔ کاربر در صورت احراز هویت یا 'anonymous') و یک پاسخ JSON با کد وضعیت 400 و کد خطای "SENSITIVE_CONTENT_DETECTED" بازمی‌گرداند. خطاهای مربوط به رمزگشایی یا فقدان بدنه نادیده گرفته می‌شوند و پردازش اجازه می‌یابد ادامه یابد.
        
        Parameters:
            request (django.http.HttpRequest): شیء درخواست Django؛ مورد انتظار است که دارای صفات `path`, `method`, `body` و `user` باشد.
        
        Returns:
            django.http.HttpResponse or None: در صورت شناسایی محتوای حساس، یک JsonResponse با وضعیت 400 بازگردانده می‌شود، در غیر این صورت None تا پردازش ادامه یابد.
        """
        if not self._is_chatbot_api(request.path):
            return None
        
        # بررسی محتوای حساس در درخواست
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
        """
        بررسی وجود محتوای حساس در یک رشته
        
        این متد بررسی می‌کند که آیا هر یک از کلیدواژه‌های حساس شناخته‌شده (تعریف‌شده در SENSITIVE_KEYWORDS) در متن ورودی وجود دارد یا خیر. مقایسه به‌صورت غیرقابل‌تفاوت بین حروف (case-insensitive) انجام می‌شود — کلیدواژه‌ها به‌صورت `lower()` گرفته می‌شوند و در متن جستجو می‌شوند. اگر هر کلیدواژه‌ای یافت شود، مقدار True برگردانده می‌شود، در غیر این صورت False.
        
        Parameters:
            content (str): متن ورودی که باید برای یافتن کلیدواژه‌های حساس بررسی شود.
        
        Returns:
            bool: True در صورتی که حداقل یکی از کلیدواژه‌های حساس در متن وجود داشته باشد، در غیر این صورت False.
        """
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword in content:
                return True
        return False