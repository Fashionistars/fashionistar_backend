"""
مدل‌های اپلیکیشن integrations
برای مدیریت یکپارچه‌سازی‌های خارجی
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from django.core.validators import RegexValidator
import uuid

User = get_user_model()


class IntegrationProvider(models.Model):
    """
    مدل ارائه‌دهندگان خدمات یکپارچه‌سازی
    """
    PROVIDER_TYPES = [
        ('sms', 'پیامک'),
        ('payment', 'پرداخت'),
        ('ai', 'هوش مصنوعی'),
        ('storage', 'ذخیره‌سازی'),
        ('notification', 'اعلان'),
        ('analytics', 'تحلیل'),
        ('other', 'سایر'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'فعال'),
        ('inactive', 'غیرفعال'),
        ('maintenance', 'در حال تعمیر'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='نام ارائه‌دهنده'
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name='شناسه یکتا'
    )
    provider_type = models.CharField(
        max_length=20,
        choices=PROVIDER_TYPES,
        verbose_name='نوع خدمات'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='وضعیت'
    )
    description = models.TextField(
        blank=True,
        verbose_name='توضیحات'
    )
    api_base_url = models.URLField(
        blank=True,
        verbose_name='آدرس پایه API'
    )
    documentation_url = models.URLField(
        blank=True,
        verbose_name='لینک مستندات'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')
    
    class Meta:
        verbose_name = 'ارائه‌دهنده خدمات'
        verbose_name_plural = 'ارائه‌دهندگان خدمات'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"


class IntegrationCredential(models.Model):
    """
    مدل ذخیره اطلاعات احراز هویت برای یکپارچه‌سازی‌ها
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='credentials',
        verbose_name='ارائه‌دهنده'
    )
    key_name = models.CharField(
        max_length=100,
        verbose_name='نام کلید'
    )
    key_value = models.TextField(
        verbose_name='مقدار کلید',
        help_text='این مقدار به صورت رمزنگاری شده ذخیره می‌شود'
    )
    is_encrypted = models.BooleanField(
        default=True,
        verbose_name='رمزنگاری شده'
    )
    environment = models.CharField(
        max_length=20,
        choices=[
            ('development', 'توسعه'),
            ('staging', 'آزمایشی'),
            ('production', 'عملیاتی'),
        ],
        default='production',
        verbose_name='محیط'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاریخ انقضا'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_credentials',
        verbose_name='ایجاد کننده'
    )
    
    class Meta:
        verbose_name = 'اطلاعات احراز هویت'
        verbose_name_plural = 'اطلاعات احراز هویت'
        unique_together = ['provider', 'key_name', 'environment']
        ordering = ['provider', 'key_name']
    
    def __str__(self):
        return f"{self.provider.name} - {self.key_name}"
    
    def is_valid(self):
        """بررسی اعتبار کلید"""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class IntegrationLog(models.Model):
    """
    مدل ثبت لاگ‌های یکپارچه‌سازی
    """
    LOG_LEVELS = [
        ('debug', 'اشکال‌زدایی'),
        ('info', 'اطلاعات'),
        ('warning', 'هشدار'),
        ('error', 'خطا'),
        ('critical', 'بحرانی'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='ارائه‌دهنده'
    )
    log_level = models.CharField(
        max_length=20,
        choices=LOG_LEVELS,
        default='info',
        verbose_name='سطح لاگ'
    )
    service_name = models.CharField(
        max_length=100,
        verbose_name='نام سرویس'
    )
    action = models.CharField(
        max_length=100,
        verbose_name='عملیات'
    )
    request_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='داده‌های درخواست'
    )
    response_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='داده‌های پاسخ'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='پیام خطا'
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='کد وضعیت'
    )
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='مدت زمان (میلی‌ثانیه)'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='integration_logs',
        verbose_name='کاربر'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='آدرس IP'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='زمان ثبت',
        db_index=True
    )
    
    class Meta:
        verbose_name = 'لاگ یکپارچه‌سازی'
        verbose_name_plural = 'لاگ‌های یکپارچه‌سازی'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'created_at']),
            models.Index(fields=['log_level', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.provider.name} - {self.action} - {self.created_at}"


class WebhookEndpoint(models.Model):
    """
    مدل مدیریت Webhook endpoints
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='webhooks',
        verbose_name='ارائه‌دهنده'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='نام webhook'
    )
    endpoint_url = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='آدرس endpoint',
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z0-9-_/]+$',
                message='آدرس endpoint فقط می‌تواند شامل حروف، اعداد، خط تیره و زیرخط باشد'
            )
        ]
    )
    secret_key = models.CharField(
        max_length=255,
        verbose_name='کلید امنیتی',
        help_text='برای تأیید امضای webhook'
    )
    events = models.JSONField(
        default=list,
        verbose_name='رویدادهای مورد نظر',
        help_text='لیست رویدادهایی که این webhook دریافت می‌کند'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    retry_count = models.IntegerField(
        default=3,
        verbose_name='تعداد تلاش مجدد'
    )
    timeout_seconds = models.IntegerField(
        default=30,
        verbose_name='زمان انتظار (ثانیه)'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')
    
    class Meta:
        verbose_name = 'Webhook Endpoint'
        verbose_name_plural = 'Webhook Endpoints'
        ordering = ['provider', 'name']
    
    def __str__(self):
        return f"{self.provider.name} - {self.name}"


class WebhookEvent(models.Model):
    """
    مدل ثبت رویدادهای دریافتی از Webhook
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name='events_received',
        verbose_name='Webhook'
    )
    event_type = models.CharField(
        max_length=100,
        verbose_name='نوع رویداد'
    )
    payload = models.JSONField(
        default=dict,
        verbose_name='محتوای رویداد'
    )
    headers = models.JSONField(
        default=dict,
        verbose_name='هدرها'
    )
    signature = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='امضای دریافتی'
    )
    is_valid = models.BooleanField(
        default=True,
        verbose_name='امضا معتبر است'
    )
    is_processed = models.BooleanField(
        default=False,
        verbose_name='پردازش شده'
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان پردازش'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='پیام خطا'
    )
    retry_count = models.IntegerField(
        default=0,
        verbose_name='تعداد تلاش'
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='زمان دریافت'
    )
    
    class Meta:
        verbose_name = 'رویداد Webhook'
        verbose_name_plural = 'رویدادهای Webhook'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['webhook', 'received_at']),
            models.Index(fields=['is_processed', 'received_at']),
        ]
    
    def __str__(self):
        return f"{self.webhook.name} - {self.event_type} - {self.received_at}"


class RateLimitRule(models.Model):
    """
    مدل قوانین محدودیت نرخ درخواست
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        IntegrationProvider,
        on_delete=models.CASCADE,
        related_name='rate_limits',
        verbose_name='ارائه‌دهنده'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='نام قانون'
    )
    endpoint_pattern = models.CharField(
        max_length=255,
        verbose_name='الگوی endpoint',
        help_text='می‌تواند شامل wildcard باشد'
    )
    max_requests = models.IntegerField(
        verbose_name='حداکثر درخواست'
    )
    time_window_seconds = models.IntegerField(
        verbose_name='بازه زمانی (ثانیه)'
    )
    scope = models.CharField(
        max_length=20,
        choices=[
            ('global', 'سراسری'),
            ('user', 'کاربر'),
            ('ip', 'آدرس IP'),
        ],
        default='user',
        verbose_name='محدوده'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')
    
    class Meta:
        verbose_name = 'قانون محدودیت نرخ'
        verbose_name_plural = 'قوانین محدودیت نرخ'
        ordering = ['provider', 'name']
    
    def __str__(self):
        return f"{self.provider.name} - {self.name} ({self.max_requests}/{self.time_window_seconds}s)"