"""
سرویس پایه برای یکپارچه‌سازی‌ها
"""
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import logging
import time
from django.conf import settings
from django.core.cache import cache
from integrations.models import IntegrationProvider, IntegrationLog, IntegrationCredential

logger = logging.getLogger(__name__)


class BaseIntegrationService(ABC):
    """
    کلاس پایه برای تمام سرویس‌های یکپارچه‌سازی
    """
    
    def __init__(self, provider_slug: str):
        """
        مقداردهی اولیه سرویس
        
        Args:
            provider_slug: شناسه یکتای ارائه‌دهنده
        """
        self.provider_slug = provider_slug
        self._provider = None
        self._credentials = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @property
    def provider(self) -> IntegrationProvider:
        """دریافت اطلاعات ارائه‌دهنده"""
        if not self._provider:
            try:
                self._provider = IntegrationProvider.objects.get(
                    slug=self.provider_slug,
                    status='active'
                )
            except IntegrationProvider.DoesNotExist:
                raise ValueError(f"Provider {self.provider_slug} not found or inactive")
        return self._provider
    
    def get_credential(self, key_name: str, environment: Optional[str] = None) -> str:
        """
        دریافت اطلاعات احراز هویت
        
        Args:
            key_name: نام کلید
            environment: محیط (اختیاری)
            
        Returns:
            مقدار کلید
        """
        if not environment:
            environment = getattr(settings, 'INTEGRATION_ENVIRONMENT', 'production')
        
        cache_key = f"integration_cred:{self.provider_slug}:{key_name}:{environment}"
        
        # بررسی کش
        cached_value = cache.get(cache_key)
        if cached_value:
            return cached_value
        
        try:
            credential = IntegrationCredential.objects.get(
                provider=self.provider,
                key_name=key_name,
                environment=environment,
                is_active=True
            )
            
            if not credential.is_valid():
                raise ValueError(f"Credential {key_name} is expired or invalid")
            
            # TODO: رمزگشایی مقدار در صورت نیاز
            value = credential.key_value
            
            # ذخیره در کش
            cache.set(cache_key, value, 3600)  # 1 hour
            
            return value
            
        except IntegrationCredential.DoesNotExist:
            raise ValueError(f"Credential {key_name} not found for {self.provider_slug}")
    
    def log_activity(self, action: str, log_level: str = 'info',
                    request_data: Optional[Dict] = None,
                    response_data: Optional[Dict] = None,
                    error_message: Optional[str] = None,
                    status_code: Optional[int] = None,
                    duration_ms: Optional[int] = None,
                    user=None, ip_address: Optional[str] = None):
        """
        ثبت لاگ فعالیت
        
        Args:
            action: عملیات انجام شده
            log_level: سطح لاگ
            request_data: داده‌های درخواست
            response_data: داده‌های پاسخ
            error_message: پیام خطا
            status_code: کد وضعیت
            duration_ms: مدت زمان
            user: کاربر
            ip_address: آدرس IP
        """
        try:
            IntegrationLog.objects.create(
                provider=self.provider,
                log_level=log_level,
                service_name=self.__class__.__name__,
                action=action,
                request_data=request_data or {},
                response_data=response_data or {},
                error_message=error_message or '',
                status_code=status_code,
                duration_ms=duration_ms,
                user=user,
                ip_address=ip_address
            )
        except Exception as e:
            self.logger.error(f"Failed to log activity: {str(e)}")
    
    def check_rate_limit(self, identifier: str, action: str) -> bool:
        """
        بررسی محدودیت نرخ درخواست
        
        Args:
            identifier: شناسه (user_id, ip, etc)
            action: نوع عملیات
            
        Returns:
            آیا مجاز است؟
        """
        # دریافت قوانین rate limit از دیتابیس
        rules = self.provider.rate_limits.filter(
            is_active=True,
            endpoint_pattern__icontains=action
        )
        
        for rule in rules:
            cache_key = f"rate_limit:{self.provider_slug}:{action}:{identifier}"
            current_count = cache.get(cache_key, 0)
            
            if current_count >= rule.max_requests:
                self.log_activity(
                    action=f"rate_limit_exceeded:{action}",
                    log_level='warning',
                    error_message=f"Rate limit exceeded for {identifier}"
                )
                return False
            
            # افزایش شمارنده
            cache.set(cache_key, current_count + 1, rule.time_window_seconds)
        
        return True
    
    @abstractmethod
    def validate_config(self) -> bool:
        """
        اعتبارسنجی تنظیمات سرویس
        
        Returns:
            آیا تنظیمات معتبر است؟
        """
        pass
    
    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        بررسی سلامت سرویس
        
        Returns:
            وضعیت سلامت سرویس
        """
        pass
    
    def execute_with_retry(self, func: callable, max_retries: int = 3,
                         retry_delay: float = 1.0, *args, **kwargs) -> Any:
        """
        اجرای تابع با قابلیت تلاش مجدد
        
        Args:
            func: تابع مورد نظر
            max_retries: حداکثر تعداد تلاش
            retry_delay: تأخیر بین تلاش‌ها
            *args: آرگومان‌های تابع
            **kwargs: آرگومان‌های کلیدی تابع
            
        Returns:
            نتیجه اجرای تابع
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Attempt {attempt + 1} failed: {str(e)}"
                )
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        
        # در صورت شکست همه تلاش‌ها
        raise last_exception