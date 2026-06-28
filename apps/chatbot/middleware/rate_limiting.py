"""
محدودسازی نرخ درخواست (Rate Limiting) برای چت‌بات
Rate Limiting Middleware for Chatbot
"""

import time
from typing import Dict, Optional
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatbotRateLimitMiddleware(MiddlewareMixin):
    """
    میان‌افزار محدودسازی نرخ درخواست برای API های چت‌بات
    """
    
    # تنظیمات پیش‌فرض rate limiting
    DEFAULT_LIMITS = {
        'chatbot_message': {
            'requests': 30,  # حداکثر 30 پیام
            'window': 60,    # در 60 ثانیه
            'description': 'ارسال پیام چت‌بات'
        },
        'chatbot_session': {
            'requests': 5,   # حداکثر 5 جلسه جدید
            'window': 300,   # در 5 دقیقه
            'description': 'ایجاد جلسه چت‌بات'
        },
        'diagnosis_support': {
            'requests': 10,  # حداکثر 10 درخواست تشخیص
            'window': 600,   # در 10 دقیقه
            'description': 'پشتیبانی تشخیصی'
        },
        'medication_info': {
            'requests': 20,  # حداکثر 20 جستجوی دارو
            'window': 300,   # در 5 دقیقه
            'description': 'اطلاعات دارویی'
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
            return self._check_ip_rate_limit(request)
        
        # برای کاربران احراز هویت شده
        return self._check_user_rate_limit(request)
    
    def _is_chatbot_api(self, path: str) -> bool:
        """
        بررسی می‌کند آیا مسیر درخواست به یکی از نقاط انتهایی (endpoints) مربوط به API چت‌بات تعلق دارد.
        
        پارامترها:
            path (str): مسیر درخواست HTTP (به صورت رشته). تابع با بررسی پیشوند مسیر تعیین می‌کند که آیا این مسیر متعلق به API چت‌بات است.
        
        مقدار بازگشتی:
            bool: True اگر مسیر با یکی از پیشوندهای شناخته‌شدهٔ API چت‌بات (مثلاً '/chatbot/api/' یا '/api/chatbot/') شروع شود، در غیر این صورت False.
        
        توضیحات اضافی:
            این تابع فقط بر مبنای مقایسهٔ پیشوندی (prefix matching) کار می‌کند و برای تصمیم‌گیری در میانجی‌ها (middleware) استفاده می‌شود تا پردازش‌های مرتبط با چت‌بات فقط روی درخواست‌های مربوط اعمال شوند.
        """
        chatbot_paths = [
            '/chatbot/api/',
            '/api/chatbot/',
        ]
        return any(path.startswith(chatbot_path) for chatbot_path in chatbot_paths)
    
    def _check_ip_rate_limit(self, request) -> Optional[JsonResponse]:
        """
        اعمال محدودیت نرخ بر اساس آدرس IP برای درخواست‌های چت‌بات (برای کاربران ناشناس).
        
        این متد آدرس کلاینت را از request گرفته، کلید کش به‌صورت `rate_limit:ip:{ip}` می‌سازد و یک محدودیت سخت‌گیرانه برای کاربران بدون احراز هویت اعمال می‌کند: حداکثر 10 درخواست در بازهٔ 300 ثانیه. در صورت رسیدن به حد، یک JsonResponse با وضعیت HTTP 429 و اطلاعات مربوط به زمان تلاش مجدد بازمی‌گرداند؛ در غیر این صورت None بازمی‌گردد تا پردازش ادامه پیدا کند.
        """
        client_ip = self._get_client_ip(request)
        cache_key = f"rate_limit:ip:{client_ip}"
        
        # محدودیت سخت‌گیرانه‌تر برای IP های ناشناس
        limit_config = {
            'requests': 10,
            'window': 300,  # 5 دقیقه
            'description': 'درخواست بدون احراز هویت'
        }
        
        return self._check_rate_limit(cache_key, limit_config, request)
    
    def _check_user_rate_limit(self, request) -> Optional[JsonResponse]:
        """
        بررسی و اعمال محدودیت نرخ درخواست برای کاربر احراز شده بر اساس نوع endpoint.
        
        این متد نوع endpoint را از مسیر درخواست استخراج می‌کند، کلید کش مخصوص کاربر و endpoint را می‌سازد و تنظیمات محدودیت را از DEFAULT_LIMITS واکشی می‌کند. اگر نوع endpoint یا تنظیمات محدودیت موجود نباشند، اجازهٔ عبور درخواست داده می‌شود (None بازگردانده می‌شود). در غیر این‌صورت، بررسی نرخ واقعی توسط متد داخلی `_check_rate_limit` انجام شده و نتیجهٔ آن (None برای اجازه یا یک `JsonResponse` با وضعیت و اطلاعات نرخ‌محدودیت در صورت عبور از حد) بازگردانده می‌شود.
        """
        user_id = request.user.id
        endpoint_type = self._get_endpoint_type(request.path)
        
        if not endpoint_type:
            return None
        
        cache_key = f"rate_limit:user:{user_id}:{endpoint_type}"
        limit_config = self.DEFAULT_LIMITS.get(endpoint_type)
        
        if not limit_config:
            return None
        
        return self._check_rate_limit(cache_key, limit_config, request)
    
    def _get_endpoint_type(self, path: str) -> Optional[str]:
        """
        نوع endpoint را از مسیر (path) تعیین می‌کند.
        
        این تابع با جستجوی زیررشته‌های مشخص در مسیر، نوع منطقیِ endpoint را برمی‌گرداند که برای انتخاب قواعد محدودسازی نرخ (DEFAULT_LIMITS) استفاده می‌شود. نگاشت فعلی:
        - 'send-message' → 'chatbot_message'
        - 'start-session' → 'chatbot_session'
        - 'diagnosis-support' → 'diagnosis_support'
        - 'medication-info' → 'medication_info'
        
        پارامترها:
            path (str): مسیر درخواست HTTP (string کامل یا بخشی از آن). توجه: جستجو به‌صورت حساس به حروف (case-sensitive) انجام می‌شود.
        
        مقدار بازگشتی:
            Optional[str]: کلید نوع endpoint مطابق نگاشت فوق یا None اگر هیچ یک از الگوها در مسیر یافت نشود.
        """
        endpoint_mappings = {
            'send-message': 'chatbot_message',
            'start-session': 'chatbot_session',
            'diagnosis-support': 'diagnosis_support',
            'medication-info': 'medication_info',
        }
        
        for endpoint, limit_type in endpoint_mappings.items():
            if endpoint in path:
                return limit_type
        
        return None
    
    def _check_rate_limit(
        self, 
        cache_key: str, 
        limit_config: Dict, 
        request
    ) -> Optional[JsonResponse]:
        """
        بررسی و اعمال محدودیت نرخ (rate limit) برای یک کلید کش مشخص با استفاده از پنجره زمانی لغزان.
        
        این متد:
        - تعداد درخواست‌های اخیر مربوط به cache_key را بازیابی می‌کند، فقط رکوردهایی را نگه می‌دارد که داخل پنجره زمانی (window) قرار دارند و بر اساس limit_config تصمیم می‌گیرد آیا درخواست فعلی مجاز است یا خیر.
        - در صورت رسیدن تعداد درخواست‌های داخل پنجره به حداکثر مجاز (limit_config['requests'])، یک JsonResponse با وضعیت HTTP 429 از طریق _create_rate_limit_response برمی‌گرداند.
        - در غیر این صورت، زمان حال را به لیست درخواست‌های اخیر اضافه و آن را دوباره در cache با TTL برابر window + 60 ثانیه ذخیره می‌کند (اثر جانبی: به‌روز‌رسانی کش).
        
        پارامترها:
        - cache_key (str): کلید استفاده‌شده در کش برای نگهداری فهرست timestampهای درخواست‌ها.
        - limit_config (Dict): پیکربندی محدودیت که باید حداقل حاوی کلیدهای 'requests' (حداکثر تعداد مجاز) و 'window' (طول پنجره به ثانیه) و 'description' (متن توصیفی) باشد.
        - request: شیء درخواست Django (برای زمینه و احتمالا گزارش‌گیری) — محتوای خود درخواست در تصمیم‌گیری مستقیم استفاده نمی‌شود اما برای تولید پاسخ و لاگ می‌تواند مفید باشد.
        
        مقدار بازگشتی:
        - Optional[JsonResponse]: در صورتی که محدودیت عبور شده باشد یک JsonResponse با کد 429 بازمی‌گردد، در غیر این صورت None برگشت می‌دهد (اجازه ادامه پردازش).
        """
        current_time = int(time.time())
        window_start = current_time - limit_config['window']
        
        # دریافت درخواست‌های فعلی از cache
        requests_data = cache.get(cache_key, [])
        
        # فیلتر کردن درخواست‌های قدیمی
        recent_requests = [
            req_time for req_time in requests_data 
            if req_time > window_start
        ]
        
        # بررسی تعداد درخواست‌ها
        if len(recent_requests) >= limit_config['requests']:
            logger.warning(
                f"Rate limit exceeded for {cache_key}. "
                f"Requests: {len(recent_requests)}/{limit_config['requests']}"
            )
            
            return self._create_rate_limit_response(limit_config, recent_requests)
        
        # اضافه کردن درخواست فعلی
        recent_requests.append(current_time)
        
        # ذخیره در cache
        cache.set(cache_key, recent_requests, limit_config['window'] + 60)
        
        return None
    
    def _create_rate_limit_response(
        self, 
        limit_config: Dict, 
        recent_requests: list
    ) -> JsonResponse:
        """
        یک پاسخ JSON با کد وضعیت 429 (Too Many Requests) ساخته و بازمی‌گرداند که نشان‌دهندهٔ عبور از محدودیت نرخ است.
        
        این متد زمان باقیمانده تا پایان پنجرهٔ نرخ را با استفاده از قدیمی‌ترین تایم‌استمپ موجود در recent_requests محاسبه می‌کند و یک پاسخ شامل پیام خطا و جزئیات محدودیت (تعداد مجاز، طول پنجره، ثانیه‌ها و دقیقه‌های قابل‌انتظار برای تلاش مجدد) تولید می‌کند. مقدار بازگردانده‌شده برای فیلدهای retry_after_seconds و retry_after_minutes هرگز منفی نیست.
        
        Parameters:
            limit_config (Dict): پیکربندی محدودیت شامل کلیدهای 'requests' (حداکثر درخواست‌ها)، 'window' (اندازه پنجره به ثانیه) و 'description' (شرح نوع درخواست).
            recent_requests (list): لیستی از timestampهای یونیکس (به ثانیه) که نشان‌دهندهٔ زمان‌های درخواست‌های اخیر در پنجرهٔ لغزان است؛ باید حداقل یک مقدار داشته باشد.
        
        Returns:
            JsonResponse: پاسخ JSON با ساختار:
              {
                "error": "محدودیت تعداد درخواست",
                "message": "...",
                "details": {
                  "limit": <int>,
                  "window_seconds": <int>,
                  "retry_after_seconds": <int>,
                  "retry_after_minutes": <int>
                }
              }
            و کد وضعیت HTTP برابر 429.
        """
        # محاسبه زمان باقی‌مانده
        oldest_request = min(recent_requests)
        time_remaining = limit_config['window'] - (int(time.time()) - oldest_request)
        
        return JsonResponse({
            'error': 'محدودیت تعداد درخواست',
            'message': f"شما برای {limit_config['description']} بیش از حد مجاز درخواست ارسال کرده‌اید.",
            'details': {
                'limit': limit_config['requests'],
                'window_seconds': limit_config['window'],
                'retry_after_seconds': max(time_remaining, 0),
                'retry_after_minutes': max(time_remaining // 60, 0)
            }
        }, status=429)
    
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
    میان‌افزار امنیتی برای چت‌بات
    """
    
    # کلمات حساس که باید فیلتر شوند
    SENSITIVE_KEYWORDS = [
        'password', 'رمز عبور', 'پسورد',
        'social security', 'کد ملی',
        'credit card', 'کارت اعتباری',
        'bank account', 'حساب بانکی'
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
                    logger.warning(
                        f"Sensitive content detected from user {request.user.id if request.user.is_authenticated else 'anonymous'}"
                    )
                    
                    return JsonResponse({
                        'error': 'محتوای حساس',
                        'message': 'لطفاً از ارسال اطلاعات حساس مانند رمز عبور یا شماره کارت خودداری کنید.',
                        'code': 'SENSITIVE_CONTENT_DETECTED'
                    }, status=400)
            except (UnicodeDecodeError, AttributeError):
                pass
        
        return None
    
    def _is_chatbot_api(self, path: str) -> bool:
        """
        بررسی می‌کند آیا مسیر درخواست به یکی از نقاط انتهایی (endpoints) مربوط به API چت‌بات تعلق دارد.
        
        پارامترها:
            path (str): مسیر درخواست HTTP (به صورت رشته). تابع با بررسی پیشوند مسیر تعیین می‌کند که آیا این مسیر متعلق به API چت‌بات است.
        
        مقدار بازگشتی:
            bool: True اگر مسیر با یکی از پیشوندهای شناخته‌شدهٔ API چت‌بات (مثلاً '/chatbot/api/' یا '/api/chatbot/') شروع شود، در غیر این صورت False.
        
        توضیحات اضافی:
            این تابع فقط بر مبنای مقایسهٔ پیشوندی (prefix matching) کار می‌کند و برای تصمیم‌گیری در میانجی‌ها (middleware) استفاده می‌شود تا پردازش‌های مرتبط با چت‌بات فقط روی درخواست‌های مربوط اعمال شوند.
        """
        chatbot_paths = [
            '/chatbot/api/',
            '/api/chatbot/',
        ]
        return any(path.startswith(chatbot_path) for chatbot_path in chatbot_paths)
    
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
            if keyword.lower() in content:
                return True
        return False