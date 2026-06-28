"""
مدل‌های یکپارچه برای ارتباط با سرویس‌های unified
Unified Models for Integration with Unified Services
"""

from django.db import models
from django.contrib.auth import get_user_model
from .base_models import BaseModel, StatusModel
from decimal import Decimal

User = get_user_model()


class UnifiedAuthIntegration(BaseModel):
    """
    مدل برای یکپارچه‌سازی با unified_auth
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='auth_integrations',
        verbose_name='کاربر'
    )
    token_type = models.CharField(
        max_length=20,
        choices=[
            ('access', 'Access Token'),
            ('refresh', 'Refresh Token'),
            ('otp', 'OTP Token'),
        ],
        verbose_name='نوع توکن'
    )
    token_value = models.TextField(
        verbose_name='مقدار توکن'
    )
    expires_at = models.DateTimeField(
        verbose_name='تاریخ انقضا'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    
    class Meta:
        verbose_name = 'یکپارچه‌سازی احراز هویت'
        verbose_name_plural = 'یکپارچه‌سازی‌های احراز هویت'
        indexes = [
            models.Index(fields=['user', 'token_type']),
            models.Index(fields=['expires_at']),
        ]


class UnifiedBillingIntegration(StatusModel):
    """
    مدل برای یکپارچه‌سازی با unified_billing
    """
    STATUS_CHOICES = [
        ('pending', 'در انتظار'),
        ('processing', 'در حال پردازش'),
        ('completed', 'تکمیل شده'),
        ('failed', 'ناموفق'),
        ('refunded', 'بازپرداخت شده'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='billing_transactions',
        verbose_name='کاربر'
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=[
            ('payment', 'پرداخت'),
            ('withdrawal', 'برداشت'),
            ('refund', 'بازپرداخت'),
            ('subscription', 'اشتراک'),
        ],
        verbose_name='نوع تراکنش'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name='مبلغ (ریال)'
    )
    gateway = models.CharField(
        max_length=20,
        choices=[
            ('zarinpal', 'زرین‌پال'),
            ('bitpay', 'بیت‌پی'),
            ('stripe', 'استرایپ'),
            ('wallet', 'کیف پول'),
        ],
        verbose_name='درگاه پرداخت'
    )
    reference_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='شناسه مرجع'
    )
    gateway_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='شناسه درگاه'
    )
    description = models.TextField(
        blank=True,
        verbose_name='توضیحات'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    
    class Meta:
        verbose_name = 'تراکنش مالی'
        verbose_name_plural = 'تراکنش‌های مالی'
        indexes = [
            models.Index(fields=['reference_id']),
            models.Index(fields=['user', 'transaction_type', '-created_at']),
        ]
    
    @property
    def amount_display(self):
        """نمایش مبلغ با فرمت مناسب"""
        return f"{self.amount:,.0f} ریال"


class UnifiedAIUsage(BaseModel):
    """
    مدل برای ردیابی استفاده از unified_ai
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ai_usage',
        verbose_name='کاربر'
    )
    service_type = models.CharField(
        max_length=30,
        choices=[
            ('chat', 'چت'),
            ('text_generation', 'تولید متن'),
            ('stt', 'تبدیل گفتار به متن'),
            ('tts', 'تبدیل متن به گفتار'),
            ('image_analysis', 'تحلیل تصویر'),
        ],
        verbose_name='نوع سرویس'
    )
    model_name = models.CharField(
        max_length=50,
        verbose_name='نام مدل'
    )
    input_tokens = models.IntegerField(
        default=0,
        verbose_name='توکن‌های ورودی'
    )
    output_tokens = models.IntegerField(
        default=0,
        verbose_name='توکن‌های خروجی'
    )
    processing_time = models.FloatField(
        verbose_name='زمان پردازش (ثانیه)'
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='هزینه (دلار)'
    )
    request_data = models.JSONField(
        default=dict,
        verbose_name='داده‌های درخواست'
    )
    response_data = models.JSONField(
        default=dict,
        verbose_name='داده‌های پاسخ'
    )
    success = models.BooleanField(
        default=True,
        verbose_name='موفقیت'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='پیام خطا'
    )
    
    class Meta:
        verbose_name = 'استفاده از AI'
        verbose_name_plural = 'استفاده‌های AI'
        indexes = [
            models.Index(fields=['user', 'service_type', '-created_at']),
            models.Index(fields=['model_name', '-created_at']),
        ]
    
    @property
    def total_tokens(self):
        """مجموع توکن‌ها"""
        return self.input_tokens + self.output_tokens


class UnifiedAccessPermission(BaseModel):
    """
    مدل برای مدیریت دسترسی‌های unified_access
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='custom_permissions',
        verbose_name='کاربر'
    )
    resource_type = models.CharField(
        max_length=50,
        verbose_name='نوع منبع'
    )
    resource_id = models.CharField(
        max_length=100,
        verbose_name='شناسه منبع'
    )
    permission_type = models.CharField(
        max_length=20,
        choices=[
            ('view', 'مشاهده'),
            ('edit', 'ویرایش'),
            ('delete', 'حذف'),
            ('share', 'اشتراک‌گذاری'),
            ('admin', 'مدیریت'),
        ],
        verbose_name='نوع دسترسی'
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='permissions_granted',
        verbose_name='اعطاکننده'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاریخ انقضا'
    )
    conditions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='شرایط دسترسی'
    )
    
    class Meta:
        verbose_name = 'دسترسی سفارشی'
        verbose_name_plural = 'دسترسی‌های سفارشی'
        unique_together = [['user', 'resource_type', 'resource_id', 'permission_type']]
        indexes = [
            models.Index(fields=['user', 'resource_type']),
            models.Index(fields=['expires_at']),
        ]


class UnifiedNotification(StatusModel):
    """
    مدل برای مدیریت اعلان‌های سیستم
    """
    STATUS_CHOICES = [
        ('pending', 'در انتظار ارسال'),
        ('sent', 'ارسال شده'),
        ('delivered', 'تحویل شده'),
        ('read', 'خوانده شده'),
        ('failed', 'ناموفق'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='کاربر'
    )
    notification_type = models.CharField(
        max_length=30,
        choices=[
            ('sms', 'پیامک'),
            ('email', 'ایمیل'),
            ('push', 'اعلان پوش'),
            ('in_app', 'درون برنامه'),
        ],
        verbose_name='نوع اعلان'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='عنوان'
    )
    content = models.TextField(
        verbose_name='محتوا'
    )
    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', 'پایین'),
            ('normal', 'معمولی'),
            ('high', 'بالا'),
            ('urgent', 'فوری'),
        ],
        default='normal',
        verbose_name='اولویت'
    )
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان‌بندی ارسال'
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان ارسال'
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان خوانده شدن'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    
    class Meta:
        verbose_name = 'اعلان'
        verbose_name_plural = 'اعلان‌ها'
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['notification_type', 'status']),
            models.Index(fields=['scheduled_for']),
        ]
    
    def mark_as_read(self):
        """علامت‌گذاری به عنوان خوانده شده"""
        from django.utils import timezone
        self.status = 'read'
        self.read_at = timezone.now()
        self.save(update_fields=['status', 'read_at', 'updated_at'])


class UnifiedRateLimit(BaseModel):
    """
    مدل برای مدیریت محدودیت‌های نرخ درخواست
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='rate_limits',
        verbose_name='کاربر'
    )
    endpoint = models.CharField(
        max_length=200,
        verbose_name='نقطه پایانی'
    )
    limit_type = models.CharField(
        max_length=20,
        choices=[
            ('api_call', 'فراخوانی API'),
            ('ai_request', 'درخواست AI'),
            ('file_upload', 'آپلود فایل'),
            ('sms_send', 'ارسال پیامک'),
        ],
        verbose_name='نوع محدودیت'
    )
    window_minutes = models.IntegerField(
        default=60,
        verbose_name='بازه زمانی (دقیقه)'
    )
    max_requests = models.IntegerField(
        verbose_name='حداکثر درخواست'
    )
    current_count = models.IntegerField(
        default=0,
        verbose_name='تعداد فعلی'
    )
    window_start = models.DateTimeField(
        verbose_name='شروع بازه'
    )
    
    class Meta:
        verbose_name = 'محدودیت نرخ'
        verbose_name_plural = 'محدودیت‌های نرخ'
        unique_together = [['user', 'endpoint', 'limit_type']]
        indexes = [
            models.Index(fields=['user', 'limit_type']),
            models.Index(fields=['window_start']),
        ]
    
    def is_limit_exceeded(self):
        """بررسی تجاوز از محدودیت"""
        from django.utils import timezone
        
        # بررسی اتمام بازه زمانی
        window_end = self.window_start + timezone.timedelta(minutes=self.window_minutes)
        if timezone.now() > window_end:
            # شروع بازه جدید
            self.window_start = timezone.now()
            self.current_count = 0
            self.save(update_fields=['window_start', 'current_count'])
            return False
        
        return self.current_count >= self.max_requests
    
    def increment(self):
        """افزایش شمارنده"""
        self.current_count += 1
        self.save(update_fields=['current_count'])


# مثال استفاده
def example_unified_integration():
    """نمونه استفاده از مدل‌های یکپارچه"""
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    
    User = get_user_model()
    user = User.objects.first()
    
    # ثبت استفاده از AI
    ai_usage = UnifiedAIUsage.objects.create(
        user=user,
        service_type='chat',
        model_name='gpt-4',
        input_tokens=150,
        output_tokens=200,
        processing_time=2.5,
        cost=Decimal('0.015'),
        request_data={'prompt': 'سلام، حالم خوب نیست'},
        response_data={'text': 'متاسفم که حالتان خوب نیست...'}
    )
    
    # ثبت تراکنش مالی
    transaction = UnifiedBillingIntegration.objects.create(
        user=user,
        transaction_type='payment',
        amount=50000,
        gateway='zarinpal',
        reference_id='TX123456',
        description='پرداخت ویزیت آنلاین'
    )
    
    # ارسال اعلان
    notification = UnifiedNotification.objects.create(
        user=user,
        notification_type='sms',
        title='یادآوری ویزیت',
        content='ویزیت شما فردا ساعت 10 صبح می‌باشد',
        priority='high',
        scheduled_for=timezone.now() + timezone.timedelta(hours=12)
    )