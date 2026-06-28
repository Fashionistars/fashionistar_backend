# apps/scheduler/admin.py
"""
Admin interface for the scheduler app.
Integrated with SoftDeleteAdminMixin for safe auditing.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from apps.common.admin_mixins import SoftDeleteAdminMixin
from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)


@admin.register(TaskDefinition)
class TaskDefinitionAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """Admin manager for TaskDefinition."""
    
    list_display = [
        'name',
        'task_type',
        'task_path',
        'queue_name',
        'is_active',
        'execution_count',
        'created_at'
    ]
    list_filter = ['task_type', 'queue_name', 'is_active', 'created_at']
    search_fields = ['name', 'task_path', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'task_type', 'description')
        }),
        ('Execution Parameters', {
            'fields': ('task_path', 'queue_name', 'default_params', 'is_active')
        }),
        ('System Information', {
            'fields': ('id', 'created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        })
    )
    
    def execution_count(self, obj):
        """Count runs."""
        count = obj.executions.count()
        return format_html(
            '<a href="{}?task_definition__id={}">{}</a>',
            reverse('admin:scheduler_taskexecution_changelist'),
            obj.id,
            count
        )
    execution_count.short_description = 'Execution Count'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """Admin manager for ScheduledTask."""
    
    list_display = [
        'name',
        'task_definition',
        'schedule_type',
        'status_badge',
        'priority',
        'last_run_at',
        'next_run_at',
        'success_rate',
        'is_overdue'
    ]
    list_filter = [
        'status',
        'schedule_type',
        'priority',
        'task_definition',
        'created_at'
    ]
    search_fields = ['name', 'task_definition__name']
    readonly_fields = [
        'id', 'last_run_at', 'next_run_at', 'total_run_count',
        'success_count', 'failure_count', 'celery_beat_id',
        'created_at', 'updated_at', 'created_by'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'task_definition', 'status', 'priority')
        }),
        ('Schedules', {
            'fields': (
                'schedule_type',
                'one_off_datetime',
                'interval_seconds',
                'cron_expression',
                'start_datetime',
                'end_datetime'
            )
        }),
        ('Execution Parameters', {
            'fields': ('params', 'max_retries', 'retry_delay')
        }),
        ('Execution Statistics', {
            'fields': (
                'last_run_at', 'next_run_at', 'total_run_count',
                'success_count', 'failure_count'
            ),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': (
                'id', 'celery_beat_id', 'created_at',
                'updated_at', 'created_by'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = ['activate_tasks', 'pause_tasks', 'run_now']
    
    def status_badge(self, obj):
        """Colored status badges."""
        colors = {
            'active': 'green',
            'paused': 'orange',
            'expired': 'red',
            'disabled': 'gray'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def success_rate(self, obj):
        """Success rate calculation."""
        if obj.total_run_count == 0:
            return '-'
        rate = (obj.success_count / obj.total_run_count) * 100
        color = 'green' if rate >= 80 else 'orange' if rate >= 50 else 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color,
            rate
        )
    success_rate.short_description = 'Success Rate'
    
    def is_overdue(self, obj):
        """Overdue status check."""
        if obj.next_run_at and obj.status == 'active':
            if obj.next_run_at < timezone.now():
                return format_html('<span style="color: red;">{}</span>', "✗ Overdue")
        return format_html('<span style="color: green;">{}</span>', "✓ On Time")
    is_overdue.short_description = 'Execution Status'
    
    def activate_tasks(self, request, queryset):
        """Activate tasks."""
        count = queryset.filter(status__in=['paused', 'disabled']).update(status='active')
        self.message_user(request, f'{count} tasks activated.')
    activate_tasks.short_description = 'Activate selected tasks'
    
    def pause_tasks(self, request, queryset):
        """Pause tasks."""
        count = queryset.filter(status='active').update(status='paused')
        self.message_user(request, f'{count} tasks paused.')
    pause_tasks.short_description = 'Pause selected tasks'
    
    def run_now(self, request, queryset):
        """Run tasks immediately."""
        from .tasks import run_scheduled_task
        count = 0
        for task in queryset.filter(status__in=['active', 'paused']):
            run_scheduled_task.delay(str(task.id))
            count += 1
        self.message_user(request, f'{count} tasks queued for execution.')
    run_now.short_description = 'Run selected tasks immediately'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    """Admin manager for TaskExecution."""
    
    list_display = [
        'task_name',
        'scheduled_task',
        'status_badge',
        'duration_display',
        'retry_count',
        'queued_at',
        'worker_name'
    ]
    list_filter = [
        'status',
        'task_definition',
        'scheduled_task',
        'worker_name',
        'queued_at'
    ]
    search_fields = [
        'celery_task_id',
        'task_definition__name',
        'scheduled_task__name'
    ]
    readonly_fields = [
        'id', 'celery_task_id', 'queued_at', 'started_at',
        'completed_at', 'duration_seconds', 'worker_name',
        'queue_name', 'created_by'
    ]
    date_hierarchy = 'queued_at'
    
    fieldsets = (
        ('Task Info', {
            'fields': (
                'task_definition', 'scheduled_task',
                'celery_task_id', 'status'
            )
        }),
        ('Parameters & Result', {
            'fields': ('params', 'result', 'error_message', 'traceback')
        }),
        ('Execution Times', {
            'fields': (
                'queued_at', 'started_at', 'completed_at',
                'duration_seconds'
            )
        }),
        ('Worker Information', {
            'fields': (
                'retry_count', 'worker_name', 'queue_name',
                'created_by'
            )
        })
    )
    
    def task_name(self, obj):
        """Get task name."""
        return obj.task_definition.name
    task_name.short_description = 'Task Name'
    
    def status_badge(self, obj):
        """Colored status badge."""
        colors = {
            'pending': 'gray',
            'running': 'blue',
            'success': 'green',
            'failed': 'red',
            'retrying': 'orange',
            'cancelled': 'black'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def duration_display(self, obj):
        """Show human-readable duration."""
        if obj.duration_seconds is not None:
            if obj.duration_seconds < 60:
                return f'{obj.duration_seconds:.2f} s'
            elif obj.duration_seconds < 3600:
                return f'{obj.duration_seconds/60:.2f} min'
            else:
                return f'{obj.duration_seconds/3600:.2f} h'
        return '-'
    duration_display.short_description = 'Execution Duration'
    
    def has_add_permission(self, request):
        return False


class TaskLogInline(admin.TabularInline):
    """Inline view of task logs."""
    model = TaskLog
    extra = 0
    readonly_fields = ['level', 'message', 'extra_data', 'created_at']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TaskLog)
class TaskLogAdmin(admin.ModelAdmin):
    """Admin manager for TaskLog."""
    
    list_display = [
        'execution_task_name',
        'level_badge',
        'message_short',
        'created_at'
    ]
    list_filter = ['level', 'created_at', 'execution__task_definition']
    search_fields = ['message', 'execution__celery_task_id']
    readonly_fields = ['id', 'execution', 'level', 'message', 'extra_data', 'created_at']
    date_hierarchy = 'created_at'
    
    def execution_task_name(self, obj):
        """Task name."""
        return obj.execution.task_definition.name
    execution_task_name.short_description = 'Task'
    
    def level_badge(self, obj):
        """Colored level badge."""
        colors = {
            'debug': 'gray',
            'info': 'blue',
            'warning': 'orange',
            'error': 'red',
            'critical': 'darkred'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.level, 'gray'),
            obj.get_level_display()
        )
    level_badge.short_description = 'Level'
    
    def message_short(self, obj):
        """Summary of message."""
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_short.short_description = 'Message'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TaskAlert)
class TaskAlertAdmin(admin.ModelAdmin):
    """Admin manager for TaskAlert."""
    
    list_display = [
        'title',
        'alert_type_badge',
        'severity_badge',
        'task_name',
        'is_resolved_badge',
        'created_at'
    ]
    list_filter = [
        'is_resolved',
        'severity',
        'alert_type',
        'created_at',
        'task_definition',
        'scheduled_task'
    ]
    search_fields = ['title', 'message']
    readonly_fields = [
        'id', 'task_definition', 'scheduled_task', 'execution',
        'alert_type', 'severity', 'title', 'message', 'details',
        'notification_sent_at', 'created_at'
    ]
    date_hierarchy = 'created_at'
    filter_horizontal = ['notified_users']
    
    fieldsets = (
        ('Alert Information', {
            'fields': (
                'alert_type', 'severity', 'title', 'message',
                'task_definition', 'scheduled_task', 'execution'
            )
        }),
        ('Details', {
            'fields': ('details',)
        }),
        ('Resolution Status', {
            'fields': (
                'is_resolved', 'resolved_at', 'resolved_by',
                'resolution_note'
            )
        }),
        ('Notifications', {
            'fields': ('notified_users', 'notification_sent_at')
        }),
        ('System Information', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['resolve_alerts', 'send_notifications']
    
    def task_name(self, obj):
        """Get related task name."""
        if obj.scheduled_task:
            return obj.scheduled_task.name
        elif obj.task_definition:
            return obj.task_definition.name
        return '-'
    task_name.short_description = 'Task'
    
    def alert_type_badge(self, obj):
        """Colored alert type badge."""
        colors = {
            'failure': 'red',
            'timeout': 'orange',
            'threshold': 'yellow',
            'missing': 'purple',
            'performance': 'blue'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.alert_type, 'gray'),
            obj.get_alert_type_display()
        )
    alert_type_badge.short_description = 'Type'
    
    def severity_badge(self, obj):
        """Colored severity badge."""
        colors = {
            'low': 'green',
            'medium': 'yellow',
            'high': 'orange',
            'critical': 'red'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.severity, 'gray'),
            obj.get_severity_display()
        )
    severity_badge.short_description = 'Severity'
    
    def is_resolved_badge(self, obj):
        """Resolution status badge."""
        if obj.is_resolved:
            return format_html('<span style="color: green;">{}</span>', "✓ Resolved")
        return format_html('<span style="color: red;">{}</span>', "✗ Unresolved")
    is_resolved_badge.short_description = 'Status'
    
    def resolve_alerts(self, request, queryset):
        """Resolve alerts."""
        count = queryset.filter(is_resolved=False).update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolved_by=request.user,
            resolution_note='Resolved by Admin'
        )
        self.message_user(request, f'{count} alerts resolved.')
    resolve_alerts.short_description = 'Mark selected alerts as resolved'
    
    def send_notifications(self, request, queryset):
        """Send notifications."""
        from .tasks import send_task_alerts
        send_task_alerts.delay()
        self.message_user(request, 'Request to dispatch notifications registered.')
    send_notifications.short_description = 'Dispatch notifications for selected alerts'