"""
مدل‌های اپ scheduler
مدیریت وظایف و زمان‌بندی‌ها
"""
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
import json
import uuid

User = get_user_model()


class TaskDefinition(models.Model):
    """
    تعریف وظایف قابل اجرا در سیستم
    """
    TASK_TYPES = [
        ('cleanup', 'پاکسازی'),
        ('report', 'گزارش‌گیری'),
        ('notification', 'اطلاع‌رسانی'),
        ('backup', 'پشتیبان‌گیری'),
        ('sync', 'همگام‌سازی'),
        ('analytics', 'تحلیل داده'),
        ('health_check', 'بررسی سلامت'),
        ('custom', 'سفارشی'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='نام وظیفه'
    )
    task_path = models.CharField(
        max_length=500,
        verbose_name='مسیر تابع',
        help_text='مثال: app_name.tasks.function_name'
    )
    task_type = models.CharField(
        max_length=20,
        choices=TASK_TYPES,
        default='custom',
        verbose_name='نوع وظیفه'
    )
    description = models.TextField(
        blank=True,
        verbose_name='توضیحات'
    )
    default_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='پارامترهای پیش‌فرض'
    )
    queue_name = models.CharField(
        max_length=100,
        default='default',
        verbose_name='نام صف'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='فعال'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_task_definitions',
        verbose_name='ایجاد کننده'
    )
    
    class Meta:
        verbose_name = 'تعریف وظیفه'
        verbose_name_plural = 'تعاریف وظایف'
        ordering = ['task_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_task_type_display()})"


class ScheduledTask(models.Model):
    """
    وظایف زمان‌بندی شده
    """
    SCHEDULE_TYPES = [
        ('once', 'یکبار'),
        ('interval', 'بازه زمانی'),
        ('cron', 'کرون'),
        ('daily', 'روزانه'),
        ('weekly', 'هفتگی'),
        ('monthly', 'ماهانه'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'فعال'),
        ('paused', 'متوقف'),
        ('expired', 'منقضی'),
        ('disabled', 'غیرفعال'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        related_name='scheduled_tasks',
        verbose_name='تعریف وظیفه'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='نام زمان‌بندی'
    )
    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPES,
        verbose_name='نوع زمان‌بندی'
    )
    
    # زمان‌بندی یکبار
    one_off_datetime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان اجرا'
    )
    
    # زمان‌بندی بازه‌ای
    interval_seconds = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name='بازه زمانی (ثانیه)'
    )
    
    # زمان‌بندی کرون
    cron_expression = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='عبارت کرون',
        help_text='مثال: 0 0 * * * (هر روز ساعت 00:00)'
    )
    
    # پارامترهای اجرا
    params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='پارامترها'
    )
    
    # وضعیت و کنترل
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='وضعیت'
    )
    priority = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        verbose_name='اولویت',
        help_text='1=بالاترین، 10=پایین‌ترین'
    )
    max_retries = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0)],
        verbose_name='حداکثر تلاش مجدد'
    )
    retry_delay = models.IntegerField(
        default=60,
        validators=[MinValueValidator(1)],
        verbose_name='تاخیر تلاش مجدد (ثانیه)'
    )
    
    # زمان‌های شروع و پایان
    start_datetime = models.DateTimeField(
        default=timezone.now,
        verbose_name='زمان شروع'
    )
    end_datetime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان پایان'
    )
    
    # آمار اجرا
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='آخرین اجرا'
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='اجرای بعدی'
    )
    total_run_count = models.IntegerField(
        default=0,
        verbose_name='تعداد کل اجراها'
    )
    success_count = models.IntegerField(
        default=0,
        verbose_name='تعداد اجرای موفق'
    )
    failure_count = models.IntegerField(
        default=0,
        verbose_name='تعداد اجرای ناموفق'
    )
    
    # Celery Beat ID (برای همگام‌سازی با django-celery-beat)
    celery_beat_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='شناسه Celery Beat'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_scheduled_tasks',
        verbose_name='ایجاد کننده'
    )
    
    class Meta:
        verbose_name = 'وظیفه زمان‌بندی شده'
        verbose_name_plural = 'وظایف زمان‌بندی شده'
        ordering = ['-priority', 'name']
        indexes = [
            models.Index(fields=['status', 'next_run_at']),
            models.Index(fields=['task_definition', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_schedule_type_display()})"


class TaskExecution(models.Model):
    """
    سابقه اجرای وظایف
    """
    STATUS_CHOICES = [
        ('pending', 'در انتظار'),
        ('running', 'در حال اجرا'),
        ('success', 'موفق'),
        ('failed', 'ناموفق'),
        ('retrying', 'تلاش مجدد'),
        ('cancelled', 'لغو شده'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scheduled_task = models.ForeignKey(
        ScheduledTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='وظیفه زمان‌بندی شده'
    )
    task_definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        related_name='executions',
        verbose_name='تعریف وظیفه'
    )
    celery_task_id = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='شناسه Celery'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='وضعیت'
    )
    params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='پارامترهای اجرا'
    )
    
    # زمان‌ها
    queued_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='زمان ورود به صف'
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان شروع'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان اتمام'
    )
    
    # نتایج
    result = models.JSONField(
        null=True,
        blank=True,
        verbose_name='نتیجه'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='پیام خطا'
    )
    traceback = models.TextField(
        blank=True,
        verbose_name='جزئیات خطا'
    )
    
    # آمار
    retry_count = models.IntegerField(
        default=0,
        verbose_name='تعداد تلاش'
    )
    duration_seconds = models.FloatField(
        null=True,
        blank=True,
        verbose_name='مدت اجرا (ثانیه)'
    )
    
    # اطلاعات اضافی
    worker_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='نام Worker'
    )
    queue_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='نام صف'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_task_executions',
        verbose_name='اجرا کننده'
    )
    
    class Meta:
        verbose_name = 'سابقه اجرا'
        verbose_name_plural = 'سوابق اجرا'
        ordering = ['-queued_at']
        indexes = [
            models.Index(fields=['status', 'queued_at']),
            models.Index(fields=['scheduled_task', 'status']),
            models.Index(fields=['celery_task_id']),
        ]
    
    def __str__(self):
        return f"{self.task_definition.name} - {self.get_status_display()} ({self.queued_at})"
    
    def calculate_duration(self):
        """محاسبه مدت زمان اجرا"""
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.duration_seconds = duration
            self.save(update_fields=['duration_seconds'])
            return duration
        return None


class TaskLog(models.Model):
    """
    لاگ‌های جزئی اجرای وظایف
    """
    LOG_LEVELS = [
        ('debug', 'اشکال‌زدایی'),
        ('info', 'اطلاعات'),
        ('warning', 'هشدار'),
        ('error', 'خطا'),
        ('critical', 'بحرانی'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='اجرا'
    )
    level = models.CharField(
        max_length=20,
        choices=LOG_LEVELS,
        default='info',
        verbose_name='سطح'
    )
    message = models.TextField(
        verbose_name='پیام'
    )
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='داده‌های اضافی'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='زمان ثبت'
    )
    
    class Meta:
        verbose_name = 'لاگ وظیفه'
        verbose_name_plural = 'لاگ‌های وظایف'
        ordering = ['execution', 'created_at']
        indexes = [
            models.Index(fields=['execution', 'level']),
        ]
    
    def __str__(self):
        return f"{self.get_level_display()}: {self.message[:50]}..."


class TaskAlert(models.Model):
    """
    هشدارهای مربوط به وظایف
    """
    ALERT_TYPES = [
        ('failure', 'خطا در اجرا'),
        ('timeout', 'اتمام زمان'),
        ('threshold', 'عبور از آستانه'),
        ('missing', 'عدم اجرا'),
        ('performance', 'کاهش کارایی'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'پایین'),
        ('medium', 'متوسط'),
        ('high', 'بالا'),
        ('critical', 'بحرانی'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='تعریف وظیفه'
    )
    scheduled_task = models.ForeignKey(
        ScheduledTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='وظیفه زمان‌بندی شده'
    )
    execution = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='اجرا'
    )
    
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        verbose_name='نوع هشدار'
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_LEVELS,
        default='medium',
        verbose_name='شدت'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='عنوان'
    )
    message = models.TextField(
        verbose_name='پیام'
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='جزئیات'
    )
    
    # وضعیت هشدار
    is_resolved = models.BooleanField(
        default=False,
        verbose_name='حل شده'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان حل'
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_task_alerts',
        verbose_name='حل کننده'
    )
    resolution_note = models.TextField(
        blank=True,
        verbose_name='یادداشت حل'
    )
    
    # اطلاع‌رسانی
    notified_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='task_alert_notifications',
        verbose_name='کاربران مطلع شده'
    )
    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='زمان ارسال اطلاع‌رسانی'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='زمان ایجاد'
    )
    
    class Meta:
        verbose_name = 'هشدار وظیفه'
        verbose_name_plural = 'هشدارهای وظایف'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['severity', 'is_resolved']),
            models.Index(fields=['alert_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_severity_display()}: {self.title}"