"""
مدل‌های Analytics برای ذخیره‌سازی و تحلیل متریک‌ها
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

logger = logging.getLogger(__name__)
User = get_user_model()


class Metric(models.Model):
    """
    مدل برای ذخیره متریک‌های سیستم
    """
    METRIC_TYPE_CHOICES = [
        ('counter', 'شمارنده'),
        ('gauge', 'سنج'),
        ('histogram', 'هیستوگرام'),
        ('timer', 'زمان‌سنج'),
    ]
    
    name = models.CharField(
        max_length=255,
        verbose_name='نام متریک',
        help_text='نام متریک برای شناسایی'
    )
    metric_type = models.CharField(
        max_length=20,
        choices=METRIC_TYPE_CHOICES,
        default='gauge',
        verbose_name='نوع متریک'
    )
    value = models.FloatField(
        verbose_name='مقدار',
        help_text='مقدار عددی متریک'
    )
    tags = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='برچسب‌ها',
        help_text='برچسب‌های اضافی برای دسته‌بندی'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان ثبت'
    )
    
    class Meta:
        verbose_name = 'متریک'
        verbose_name_plural = 'متریک‌ها'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['name', 'timestamp']),
            models.Index(fields=['metric_type', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.name}: {self.value} ({self.timestamp})"


class UserActivity(models.Model):
    """
    مدل برای ردیابی فعالیت‌های کاربران
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='کاربر'
    )
    action = models.CharField(
        max_length=100,
        verbose_name='عمل انجام شده',
        help_text='نوع عمل انجام شده توسط کاربر'
    )
    resource = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='منبع',
        help_text='منبع یا بخشی که کاربر با آن تعامل کرده'
    )
    resource_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='شناسه منبع'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='آدرس IP'
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name='User Agent'
    )
    session_id = models.CharField(
        max_length=40,
        blank=True,
        verbose_name='شناسه نشست'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان انجام'
    )
    
    class Meta:
        verbose_name = 'فعالیت کاربر'
        verbose_name_plural = 'فعالیت‌های کاربران'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username}: {self.action} ({self.timestamp})"


class PerformanceMetric(models.Model):
    """
    مدل برای متریک‌های عملکرد API
    """
    endpoint = models.CharField(
        max_length=255,
        verbose_name='نقطه انتهایی',
        help_text='مسیر API endpoint'
    )
    method = models.CharField(
        max_length=10,
        verbose_name='متد HTTP',
        help_text='نوع درخواست HTTP'
    )
    response_time_ms = models.PositiveIntegerField(
        verbose_name='زمان پاسخ (میلی‌ثانیه)'
    )
    status_code = models.PositiveIntegerField(
        verbose_name='کد وضعیت HTTP'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='کاربر'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='پیام خطا'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان درخواست'
    )
    
    class Meta:
        verbose_name = 'متریک عملکرد'
        verbose_name_plural = 'متریک‌های عملکرد'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['endpoint', 'timestamp']),
            models.Index(fields=['status_code', 'timestamp']),
            models.Index(fields=['response_time_ms']),
        ]
    
    def __str__(self):
        return f"{self.method} {self.endpoint}: {self.response_time_ms}ms ({self.status_code})"


class BusinessMetric(models.Model):
    """
    مدل برای متریک‌های کسب و کار
    """
    metric_name = models.CharField(
        max_length=100,
        verbose_name='نام متریک کسب و کار'
    )
    value = models.FloatField(
        verbose_name='مقدار'
    )
    period_start = models.DateTimeField(
        verbose_name='شروع دوره'
    )
    period_end = models.DateTimeField(
        verbose_name='پایان دوره'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان ایجاد'
    )
    
    class Meta:
        verbose_name = 'متریک کسب و کار'
        verbose_name_plural = 'متریک‌های کسب و کار'
        ordering = ['-created_at']
        unique_together = ['metric_name', 'period_start', 'period_end']
        indexes = [
            models.Index(fields=['metric_name', 'period_start']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.metric_name}: {self.value} ({self.period_start.date()})"


class AlertRule(models.Model):
    """
    مدل برای قوانین هشدار
    """
    OPERATOR_CHOICES = [
        ('gt', 'بزرگتر از'),
        ('gte', 'بزرگتر مساوی'),
        ('lt', 'کوچکتر از'),
        ('lte', 'کوچکتر مساوی'),
        ('eq', 'مساوی'),
        ('ne', 'نامساوی'),
    ]
    
    SEVERITY_CHOICES = [
        ('low', 'کم'),
        ('medium', 'متوسط'),
        ('high', 'بالا'),
        ('critical', 'بحرانی'),
    ]
    
    name = models.CharField(
        max_length=100,
        verbose_name='نام قانون'
    )
    metric_name = models.CharField(
        max_length=255,
        verbose_name='نام متریک'
    )
    operator = models.CharField(
        max_length=5,
        choices=OPERATOR_CHOICES,
        verbose_name='عملگر مقایسه'
    )
    threshold = models.FloatField(
        verbose_name='آستانه'
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='medium',
        verbose_name='سطح اهمیت'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    description = models.TextField(
        blank=True,
        verbose_name='توضیحات'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان ایجاد'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='زمان بروزرسانی'
    )
    
    class Meta:
        verbose_name = 'قانون هشدار'
        verbose_name_plural = 'قوانین هشدار'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['metric_name', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name}: {self.metric_name} {self.operator} {self.threshold}"


class Alert(models.Model):
    """
    مدل برای هشدارهای تولید شده
    """
    STATUS_CHOICES = [
        ('firing', 'در حال اجرا'),
        ('resolved', 'حل شده'),
        ('suppressed', 'سرکوب شده'),
    ]
    
    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        verbose_name='قانون'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='firing',
        verbose_name='وضعیت'
    )
    metric_value = models.FloatField(
        verbose_name='مقدار متریک'
    )
    message = models.TextField(
        verbose_name='پیام هشدار'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='اطلاعات اضافی'
    )
    fired_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان تولید'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان حل'
    )
    
    class Meta:
        verbose_name = 'هشدار'
        verbose_name_plural = 'هشدارها'
        ordering = ['-fired_at']
        indexes = [
            models.Index(fields=['rule', 'status']),
            models.Index(fields=['status', 'fired_at']),
        ]
    
    def __str__(self):
        return f"{self.rule.name}: {self.status} ({self.fired_at})"