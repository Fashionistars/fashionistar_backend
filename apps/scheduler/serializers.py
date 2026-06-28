# apps/scheduler/serializers.py
"""
Serializers for the scheduler app.
"""
from rest_framework import serializers
from django.utils import timezone

from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)


class TaskDefinitionSerializer(serializers.ModelSerializer):
    """Serializer for TaskDefinition."""
    
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
        """Total run count."""
        return obj.executions.count()
    
    def validate_task_path(self, value):
        """Validate function path."""
        try:
            # Check for correct format
            if '.' not in value:
                raise serializers.ValidationError(
                    "Function path must be in module.function format"
                )
            return value
        except Exception as e:
            raise serializers.ValidationError(f"Invalid function path: {str(e)}")
    
    def validate_default_params(self, value):
        """Validate default parameters."""
        if value and not isinstance(value, dict):
            raise serializers.ValidationError("Parameters must be in dictionary format")
        return value


class ScheduledTaskSerializer(serializers.ModelSerializer):
    """Serializer for ScheduledTask."""
    
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
        """Calculate success rate."""
        if obj.total_run_count == 0:
            return None
        return round((obj.success_count / obj.total_run_count) * 100, 2)
    
    def get_is_overdue(self, obj):
        """Check if overdue."""
        if obj.next_run_at and obj.status == 'active':
            return obj.next_run_at < timezone.now()
        return False
    
    def validate(self, attrs):
        """General validation."""
        schedule_type = attrs.get('schedule_type')
        
        # Check required fields based on schedule type
        if schedule_type == 'once' and not attrs.get('one_off_datetime'):
            raise serializers.ValidationError({
                'one_off_datetime': 'For one-off schedules, execution time is required.'
            })
        
        if schedule_type == 'interval' and not attrs.get('interval_seconds'):
            raise serializers.ValidationError({
                'interval_seconds': 'For interval schedules, interval seconds is required.'
            })
        
        if schedule_type == 'cron' and not attrs.get('cron_expression'):
            raise serializers.ValidationError({
                'cron_expression': 'For cron schedules, cron expression is required.'
            })
        
        # Verify start and end times
        start_datetime = attrs.get('start_datetime')
        end_datetime = attrs.get('end_datetime')
        
        if end_datetime and start_datetime and end_datetime <= start_datetime:
            raise serializers.ValidationError({
                'end_datetime': 'End time must be after start time.'
            })
        
        return attrs


class TaskExecutionSerializer(serializers.ModelSerializer):
    """Serializer for TaskExecution."""
    
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
        """Task name."""
        return obj.task_definition.name
    
    def get_log_count(self, obj):
        """Log count."""
        return obj.logs.count()


class TaskExecutionDetailSerializer(TaskExecutionSerializer):
    """Serializer for detailed TaskExecution including logs."""
    
    logs = serializers.SerializerMethodField()
    
    class Meta(TaskExecutionSerializer.Meta):
        fields = TaskExecutionSerializer.Meta.fields + ['logs']
    
    def get_logs(self, obj):
        """Logs list."""
        logs = obj.logs.all().order_by('created_at')
        return TaskLogSerializer(logs, many=True).data


class TaskLogSerializer(serializers.ModelSerializer):
    """Serializer for TaskLog."""
    
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
    """Serializer for TaskAlert."""
    
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
        """Related task name."""
        if obj.scheduled_task:
            return obj.scheduled_task.name
        elif obj.task_definition:
            return obj.task_definition.name
        return None


class TaskAlertResolveSerializer(serializers.Serializer):
    """Serializer for resolving task alerts."""
    
    resolution_note = serializers.CharField(
        required=True,
        min_length=10,
        help_text='Description of how the issue was resolved.'
    )


class TaskExecutionCreateSerializer(serializers.Serializer):
    """Serializer for manual task run creation."""
    
    task_definition_id = serializers.UUIDField(
        required=True,
        help_text='Task definition ID'
    )
    params = serializers.JSONField(
        required=False,
        default=dict,
        help_text='Execution parameters'
    )
    priority = serializers.IntegerField(
        required=False,
        default=5,
        min_value=1,
        max_value=10,
        help_text='Execution priority (1=High, 10=Low)'
    )
    
    def validate_task_definition_id(self, value):
        """Check if task definition exists."""
        try:
            TaskDefinition.objects.get(id=value, is_active=True)
            return value
        except TaskDefinition.DoesNotExist:
            raise serializers.ValidationError(
                "Task definition with this ID was not found or is inactive."
            )


class TaskStatisticsSerializer(serializers.Serializer):
    """Serializer for task statistics."""
    
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