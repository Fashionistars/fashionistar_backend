"""
مدل‌های مدیریت DevOps و Environment Configuration
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
import json
from typing import Dict, Any, Optional
from encrypted_model_fields.fields import EncryptedTextField
import uuid


class EnvironmentConfig(models.Model):
    """مدیریت تنظیمات محیط‌های مختلف"""
    
    ENVIRONMENT_CHOICES = [
        ('development', 'Development'),
        ('staging', 'Staging'),
        ('production', 'Production'),
        ('testing', 'Testing'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="نام محیط",
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_-]+$',
            message='نام محیط فقط می‌تواند شامل حروف، اعداد، _ و - باشد'
        )]
    )
    environment_type = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        verbose_name="نوع محیط"
    )
    description = models.TextField(
        blank=True,
        verbose_name="توضیحات"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاریخ به‌روزرسانی"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="ایجاد شده توسط"
    )
    
    class Meta:
        verbose_name = "تنظیمات محیط"
        verbose_name_plural = "تنظیمات محیط‌ها"
        ordering = ['-created_at']
        
    def __str__(self) -> str:
        return f"{self.name} ({self.get_environment_type_display()})"


class SecretConfig(models.Model):
    """مدیریت رمزهای رمزنگاری شده"""
    
    CATEGORY_CHOICES = [
        ('database', 'Database'),
        ('api_key', 'API Key'),
        ('oauth', 'OAuth'),
        ('smtp', 'SMTP'),
        ('sms', 'SMS'),
        ('payment', 'Payment Gateway'),
        ('ssl', 'SSL Certificate'),
        ('encryption', 'Encryption Key'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='secrets',
        verbose_name="محیط"
    )
    key_name = models.CharField(
        max_length=100,
        verbose_name="نام کلید",
        validators=[RegexValidator(
            regex=r'^[A-Z][A-Z0-9_]*$',
            message='نام کلید باید با حرف بزرگ شروع شود و فقط شامل حروف بزرگ، اعداد و _ باشد'
        )]
    )
    encrypted_value = EncryptedTextField(
        verbose_name="مقدار رمزنگاری شده"
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='other',
        verbose_name="دسته‌بندی"
    )
    description = models.TextField(
        blank=True,
        verbose_name="توضیحات"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاریخ انقضا"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاریخ به‌روزرسانی"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="ایجاد شده توسط"
    )
    
    class Meta:
        verbose_name = "تنظیمات محرمانه"
        verbose_name_plural = "تنظیمات محرمانه"
        unique_together = [['environment', 'key_name']]
        ordering = ['-created_at']
        
    def __str__(self) -> str:
        return f"{self.key_name} ({self.environment.name})"
    
    def clean(self):
        """اعتبارسنجی مدل"""
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError("تاریخ انقضا نمی‌تواند در گذشته باشد")
    
    @property
    def is_expired(self) -> bool:
        """بررسی انقضای secret"""
        return self.expires_at and self.expires_at <= timezone.now()


class DeploymentHistory(models.Model):
    """تاریخچه deploy ها"""
    
    STATUS_CHOICES = [
        ('pending', 'در انتظار'),
        ('running', 'در حال اجرا'),
        ('success', 'موفق'),
        ('failed', 'ناموفق'),
        ('cancelled', 'لغو شده'),
        ('rollback', 'بازگشت'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='deployments',
        verbose_name="محیط"
    )
    version = models.CharField(
        max_length=50,
        verbose_name="نسخه"
    )
    commit_hash = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="هش کامیت",
        validators=[RegexValidator(
            regex=r'^[a-f0-9]{40}$',
            message='هش کامیت باید 40 کاراکتر hexadecimal باشد'
        )]
    )
    branch = models.CharField(
        max_length=100,
        default='main',
        verbose_name="شاخه"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="وضعیت"
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="شروع در"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تکمیل در"
    )
    deployed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="deploy شده توسط"
    )
    deployment_logs = models.TextField(
        blank=True,
        verbose_name="لاگ‌های deployment"
    )
    rollback_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rollbacks',
        verbose_name="بازگشت از"
    )
    artifacts_url = models.URLField(
        blank=True,
        verbose_name="URL آرتیفکت‌ها"
    )
    
    class Meta:
        verbose_name = "تاریخچه Deployment"
        verbose_name_plural = "تاریخچه Deployment ها"
        ordering = ['-started_at']
        
    def __str__(self) -> str:
        return f"{self.environment.name} - {self.version} ({self.get_status_display()})"
    
    @property
    def duration(self) -> Optional[timezone.timedelta]:
        """مدت زمان deployment"""
        if self.completed_at:
            return self.completed_at - self.started_at
        return None


class HealthCheck(models.Model):
    """نتایج health check ها"""
    
    STATUS_CHOICES = [
        ('healthy', 'سالم'),
        ('warning', 'هشدار'),
        ('critical', 'بحرانی'),
        ('unknown', 'نامشخص'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='health_checks',
        verbose_name="محیط"
    )
    service_name = models.CharField(
        max_length=100,
        verbose_name="نام سرویس"
    )
    endpoint_url = models.URLField(
        verbose_name="URL endpoint"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name="وضعیت"
    )
    response_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name="زمان پاسخ (میلی‌ثانیه)"
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="کد وضعیت HTTP"
    )
    response_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="داده‌های پاسخ"
    )
    error_message = models.TextField(
        blank=True,
        verbose_name="پیام خطا"
    )
    checked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان بررسی"
    )
    
    class Meta:
        verbose_name = "بررسی سلامت"
        verbose_name_plural = "بررسی‌های سلامت"
        ordering = ['-checked_at']
        indexes = [
            models.Index(fields=['environment', 'service_name', '-checked_at']),
            models.Index(fields=['status', '-checked_at']),
        ]
        
    def __str__(self) -> str:
        return f"{self.service_name} ({self.environment.name}) - {self.get_status_display()}"


class ServiceMonitoring(models.Model):
    """مانیتورینگ سرویس‌های مختلف"""
    
    SERVICE_TYPES = [
        ('web', 'Web Server'),
        ('database', 'Database'),
        ('cache', 'Cache'),
        ('queue', 'Message Queue'),
        ('storage', 'Object Storage'),
        ('proxy', 'Reverse Proxy'),
        ('monitoring', 'Monitoring'),
        ('external', 'External Service'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        EnvironmentConfig,
        on_delete=models.CASCADE,
        related_name='monitored_services',
        verbose_name="محیط"
    )
    service_name = models.CharField(
        max_length=100,
        verbose_name="نام سرویس"
    )
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_TYPES,
        verbose_name="نوع سرویس"
    )
    health_check_url = models.URLField(
        verbose_name="URL health check"
    )
    check_interval = models.PositiveIntegerField(
        default=300,  # 5 minutes
        verbose_name="فاصله بررسی (ثانیه)"
    )
    timeout = models.PositiveIntegerField(
        default=30,
        verbose_name="Timeout (ثانیه)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال"
    )
    alert_on_failure = models.BooleanField(
        default=True,
        verbose_name="هشدار در صورت خرابی"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاریخ به‌روزرسانی"
    )
    
    class Meta:
        verbose_name = "مانیتورینگ سرویس"
        verbose_name_plural = "مانیتورینگ سرویس‌ها"
        unique_together = [['environment', 'service_name']]
        ordering = ['service_name']
        
    def __str__(self) -> str:
        return f"{self.service_name} ({self.environment.name})"