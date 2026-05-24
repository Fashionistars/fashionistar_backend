"""
Serializers برای اپ scheduler
"""
from rest_framework import serializers
from django.utils import timezone
from typing import Dict, Any
import json

from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)


class TaskDefinitionSerializer(serializers.ModelSerializer):
    """سریالایزر تعریف وظایف"""
    
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True
    )
    execution_count = serializers.SerializerMethodField()
    
    class Meta:
        model = TaskDefinition
        fields = [
            'id',
            'name',
            'task_path',
            'task_type',
            'description',
            'default_params',
            'queue_name',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
            'execution_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_execution_count(self, obj):
        """تعداد کل اجراها"""
        return obj.executions.count()
    
    def validate_task_path(self, value):
        """اعتبارسنجی مسیر تابع"""
        try:
            # بررسی فرمت صحیح
            if '.' not in value:
                raise serializers.ValidationError(
                    "مسیر تابع باید به فرمت module.function باشد"
                )
            
            # بررسی امکان import (اختیاری)
            # module_path, function_name = value.rsplit('.', 1)
            # importlib.import_module(module_path)
            
            return value
        except Exception as e:
            raise serializers.ValidationError(f"مسیر تابع نامعتبر است: {str(e)}")
    
    def validate_default_params(self, value):
        """اعتبارسنجی پارامترهای پیش‌فرض"""
        if value and not isinstance(value, dict):
            raise serializers.ValidationError("پارامترها باید به صورت dictionary باشند")
        return value


class ScheduledTaskSerializer(serializers.ModelSerializer):
    """سریالایزر وظایف زمان‌بندی شده"""
    
    task_definition_name = serializers.CharField(
        source='task_definition.name',
        read_only=True
    )
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True
    )
    success_rate = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = ScheduledTask
        fields = [
            'id',
            'task_definition',
            'task_definition_name',
            'name',
            'schedule_type',
            'one_off_datetime',
            'interval_seconds',
            'cron_expression',
            'params',
            'status',
            'priority',
            'max_retries',
            'retry_delay',
            'start_datetime',
            'end_datetime',
            'last_run_at',
            'next_run_at',
            'total_run_count',
            'success_count',
            'failure_count',
            'success_rate',
            'is_overdue',
            'celery_beat_id',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name'
        ]
        read_only_fields = [
            'id', 'last_run_at', 'next_run_at', 'total_run_count',
            'success_count', 'failure_count', 'celery_beat_id',
            'created_at', 'updated_at', 'created_by'
        ]
    
    def get_success_rate(self, obj):
        """محاسبه نرخ موفقیت"""
        if obj.total_run_count == 0:
            return None
        return round((obj.success_count / obj.total_run_count) * 100, 2)
    
    def get_is_overdue(self, obj):
        """بررسی عقب‌افتادگی"""
        if obj.next_run_at and obj.status == 'active':
            return obj.next_run_at < timezone.now()
        return False
    
    def validate(self, attrs):
        """اعتبارسنجی کلی"""
        schedule_type = attrs.get('schedule_type')
        
        # بررسی فیلدهای مورد نیاز برای هر نوع زمان‌بندی
        if schedule_type == 'once' and not attrs.get('one_off_datetime'):
            raise serializers.ValidationError({
                'one_off_datetime': 'برای زمان‌بندی یکبار، زمان اجرا الزامی است'
            })
        
        if schedule_type == 'interval' and not attrs.get('interval_seconds'):
            raise serializers.ValidationError({
                'interval_seconds': 'برای زمان‌بندی بازه‌ای، بازه زمانی الزامی است'
            })
        
        if schedule_type == 'cron' and not attrs.get('cron_expression'):
            raise serializers.ValidationError({
                'cron_expression': 'برای زمان‌بندی کرون، عبارت کرون الزامی است'
            })
        
        # بررسی زمان شروع و پایان
        start_datetime = attrs.get('start_datetime')
        end_datetime = attrs.get('end_datetime')
        
        if end_datetime and start_datetime and end_datetime <= start_datetime:
            raise serializers.ValidationError({
                'end_datetime': 'زمان پایان باید بعد از زمان شروع باشد'
            })
        
        return attrs


class TaskExecutionSerializer(serializers.ModelSerializer):
    """سریالایزر سوابق اجرا"""
    
    task_name = serializers.SerializerMethodField()
    scheduled_task_name = serializers.CharField(
        source='scheduled_task.name',
        read_only=True
    )
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True
    )
    log_count = serializers.SerializerMethodField()
    
    class Meta:
        model = TaskExecution
        fields = [
            'id',
            'scheduled_task',
            'scheduled_task_name',
            'task_definition',
            'task_name',
            'celery_task_id',
            'status',
            'params',
            'queued_at',
            'started_at',
            'completed_at',
            'result',
            'error_message',
            'traceback',
            'retry_count',
            'duration_seconds',
            'worker_name',
            'queue_name',
            'created_by',
            'created_by_name',
            'log_count'
        ]
        read_only_fields = [
            'id', 'celery_task_id', 'queued_at', 'started_at',
            'completed_at', 'duration_seconds', 'worker_name',
            'queue_name', 'created_by'
        ]
    
    def get_task_name(self, obj):
        """نام وظیفه"""
        return obj.task_definition.name
    
    def get_log_count(self, obj):
        """تعداد لاگ‌ها"""
        return obj.logs.count()


class TaskExecutionDetailSerializer(TaskExecutionSerializer):
    """سریالایزر جزئیات سوابق اجرا با لاگ‌ها"""
    
    logs = serializers.SerializerMethodField()
    
    class Meta(TaskExecutionSerializer.Meta):
        fields = TaskExecutionSerializer.Meta.fields + ['logs']
    
    def get_logs(self, obj):
        """لیست لاگ‌ها"""
        logs = obj.logs.all().order_by('created_at')
        return TaskLogSerializer(logs, many=True).data


class TaskLogSerializer(serializers.ModelSerializer):
    """سریالایزر لاگ‌های وظایف"""
    
    level_display = serializers.CharField(
        source='get_level_display',
        read_only=True
    )
    
    class Meta:
        model = TaskLog
        fields = [
            'id',
            'execution',
            'level',
            'level_display',
            'message',
            'extra_data',
            'created_at'
        ]
        read_only_fields = ['id', 'execution', 'created_at']


class TaskAlertSerializer(serializers.ModelSerializer):
    """سریالایزر هشدارهای وظایف"""
    
    task_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.CharField(
        source='resolved_by.get_full_name',
        read_only=True
    )
    alert_type_display = serializers.CharField(
        source='get_alert_type_display',
        read_only=True
    )
    severity_display = serializers.CharField(
        source='get_severity_display',
        read_only=True
    )
    
    class Meta:
        model = TaskAlert
        fields = [
            'id',
            'task_definition',
            'scheduled_task',
            'execution',
            'task_name',
            'alert_type',
            'alert_type_display',
            'severity',
            'severity_display',
            'title',
            'message',
            'details',
            'is_resolved',
            'resolved_at',
            'resolved_by',
            'resolved_by_name',
            'resolution_note',
            'notified_users',
            'notification_sent_at',
            'created_at'
        ]
        read_only_fields = [
            'id', 'task_definition', 'scheduled_task', 'execution',
            'alert_type', 'severity', 'title', 'message', 'details',
            'notification_sent_at', 'created_at'
        ]
    
    def get_task_name(self, obj):
        """نام وظیفه مرتبط"""
        if obj.scheduled_task:
            return obj.scheduled_task.name
        elif obj.task_definition:
            return obj.task_definition.name
        return None


class TaskAlertResolveSerializer(serializers.Serializer):
    """سریالایزر حل کردن هشدار"""
    
    resolution_note = serializers.CharField(
        required=True,
        min_length=10,
        help_text='توضیحات نحوه حل مشکل'
    )


class TaskExecutionCreateSerializer(serializers.Serializer):
    """سریالایزر ایجاد اجرای دستی"""
    
    task_definition_id = serializers.UUIDField(
        required=True,
        help_text='شناسه تعریف وظیفه'
    )
    params = serializers.JSONField(
        required=False,
        default=dict,
        help_text='پارامترهای اجرا'
    )
    priority = serializers.IntegerField(
        required=False,
        default=5,
        min_value=1,
        max_value=10,
        help_text='اولویت اجرا (1=بالا، 10=پایین)'
    )
    
    def validate_task_definition_id(self, value):
        """بررسی وجود task definition"""
        try:
            TaskDefinition.objects.get(id=value, is_active=True)
            return value
        except TaskDefinition.DoesNotExist:
            raise serializers.ValidationError(
                "تعریف وظیفه با این شناسه یافت نشد یا غیرفعال است"
            )


class TaskStatisticsSerializer(serializers.Serializer):
    """سریالایزر آمار وظایف"""
    
    total_definitions = serializers.IntegerField()
    active_definitions = serializers.IntegerField()
    total_scheduled = serializers.IntegerField()
    active_scheduled = serializers.IntegerField()
    total_executions = serializers.IntegerField()
    running_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_duration = serializers.FloatField()
    unresolved_alerts = serializers.IntegerField()
    critical_alerts = serializers.IntegerField()