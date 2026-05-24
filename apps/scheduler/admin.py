"""
Admin interface برای اپ scheduler
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from django.db.models import Count, Q
from .models import (
    TaskDefinition,
    ScheduledTask,
    TaskExecution,
    TaskLog,
    TaskAlert
)


@admin.register(TaskDefinition)
class TaskDefinitionAdmin(admin.ModelAdmin):
    """مدیریت تعاریف وظایف"""
    
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
        ('اطلاعات اصلی', {
            'fields': ('name', 'task_type', 'description')
        }),
        ('تنظیمات اجرا', {
            'fields': ('task_path', 'queue_name', 'default_params', 'is_active')
        }),
        ('اطلاعات سیستمی', {
            'fields': ('id', 'created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        })
    )
    
    def execution_count(self, obj):
        """تعداد اجراها"""
        count = obj.executions.count()
        return format_html(
            '<a href="{}?task_definition__id={}">{}</a>',
            reverse('admin:scheduler_taskexecution_changelist'),
            obj.id,
            count
        )
    execution_count.short_description = 'تعداد اجرا'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    """مدیریت وظایف زمان‌بندی شده"""
    
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
        ('اطلاعات اصلی', {
            'fields': ('name', 'task_definition', 'status', 'priority')
        }),
        ('زمان‌بندی', {
            'fields': (
                'schedule_type',
                'one_off_datetime',
                'interval_seconds',
                'cron_expression',
                'start_datetime',
                'end_datetime'
            )
        }),
        ('تنظیمات اجرا', {
            'fields': ('params', 'max_retries', 'retry_delay')
        }),
        ('آمار اجرا', {
            'fields': (
                'last_run_at', 'next_run_at', 'total_run_count',
                'success_count', 'failure_count'
            ),
            'classes': ('collapse',)
        }),
        ('اطلاعات سیستمی', {
            'fields': (
                'id', 'celery_beat_id', 'created_at',
                'updated_at', 'created_by'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = ['activate_tasks', 'pause_tasks', 'run_now']
    
    def status_badge(self, obj):
        """نمایش وضعیت با رنگ"""
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
    status_badge.short_description = 'وضعیت'
    
    def success_rate(self, obj):
        """نرخ موفقیت"""
        if obj.total_run_count == 0:
            return '-'
        rate = (obj.success_count / obj.total_run_count) * 100
        color = 'green' if rate >= 80 else 'orange' if rate >= 50 else 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color,
            rate
        )
    success_rate.short_description = 'نرخ موفقیت'
    
    def is_overdue(self, obj):
        """وضعیت عقب‌افتادگی"""
        if obj.next_run_at and obj.status == 'active':
            if obj.next_run_at < timezone.now():
                return format_html('<span style="color: red;">✗ عقب‌افتاده</span>')
        return format_html('<span style="color: green;">✓ به موقع</span>')
    is_overdue.short_description = 'وضعیت اجرا'
    
    def activate_tasks(self, request, queryset):
        """فعال کردن وظایف"""
        count = queryset.filter(status__in=['paused', 'disabled']).update(status='active')
        self.message_user(request, f'{count} وظیفه فعال شد.')
    activate_tasks.short_description = 'فعال کردن وظایف انتخاب شده'
    
    def pause_tasks(self, request, queryset):
        """متوقف کردن وظایف"""
        count = queryset.filter(status='active').update(status='paused')
        self.message_user(request, f'{count} وظیفه متوقف شد.')
    pause_tasks.short_description = 'متوقف کردن وظایف انتخاب شده'
    
    def run_now(self, request, queryset):
        """اجرای فوری"""
        from .tasks import run_scheduled_task
        count = 0
        for task in queryset.filter(status__in=['active', 'paused']):
            run_scheduled_task.delay(str(task.id))
            count += 1
        self.message_user(request, f'{count} وظیفه برای اجرا ارسال شد.')
    run_now.short_description = 'اجرای فوری وظایف انتخاب شده'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    """مدیریت سوابق اجرا"""
    
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
        ('اطلاعات وظیفه', {
            'fields': (
                'task_definition', 'scheduled_task',
                'celery_task_id', 'status'
            )
        }),
        ('پارامترها و نتیجه', {
            'fields': ('params', 'result', 'error_message', 'traceback')
        }),
        ('زمان‌ها', {
            'fields': (
                'queued_at', 'started_at', 'completed_at',
                'duration_seconds'
            )
        }),
        ('اطلاعات اجرا', {
            'fields': (
                'retry_count', 'worker_name', 'queue_name',
                'created_by'
            )
        })
    )
    
    def task_name(self, obj):
        """نام وظیفه"""
        return obj.task_definition.name
    task_name.short_description = 'نام وظیفه'
    
    def status_badge(self, obj):
        """نمایش وضعیت با رنگ"""
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
    status_badge.short_description = 'وضعیت'
    
    def duration_display(self, obj):
        """نمایش مدت زمان"""
        if obj.duration_seconds:
            if obj.duration_seconds < 60:
                return f'{obj.duration_seconds:.2f} ثانیه'
            elif obj.duration_seconds < 3600:
                return f'{obj.duration_seconds/60:.2f} دقیقه'
            else:
                return f'{obj.duration_seconds/3600:.2f} ساعت'
        return '-'
    duration_display.short_description = 'مدت اجرا'
    
    def has_add_permission(self, request):
        """غیرفعال کردن افزودن دستی"""
        return False


class TaskLogInline(admin.TabularInline):
    """نمایش inline لاگ‌ها"""
    model = TaskLog
    extra = 0
    readonly_fields = ['level', 'message', 'extra_data', 'created_at']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TaskLog)
class TaskLogAdmin(admin.ModelAdmin):
    """مدیریت لاگ‌های وظایف"""
    
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
        """نام وظیفه"""
        return obj.execution.task_definition.name
    execution_task_name.short_description = 'وظیفه'
    
    def level_badge(self, obj):
        """نمایش سطح با رنگ"""
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
    level_badge.short_description = 'سطح'
    
    def message_short(self, obj):
        """خلاصه پیام"""
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_short.short_description = 'پیام'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TaskAlert)
class TaskAlertAdmin(admin.ModelAdmin):
    """مدیریت هشدارهای وظایف"""
    
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
        ('اطلاعات هشدار', {
            'fields': (
                'alert_type', 'severity', 'title', 'message',
                'task_definition', 'scheduled_task', 'execution'
            )
        }),
        ('جزئیات', {
            'fields': ('details',)
        }),
        ('وضعیت حل', {
            'fields': (
                'is_resolved', 'resolved_at', 'resolved_by',
                'resolution_note'
            )
        }),
        ('اطلاع‌رسانی', {
            'fields': ('notified_users', 'notification_sent_at')
        }),
        ('اطلاعات سیستمی', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['resolve_alerts', 'send_notifications']
    
    def task_name(self, obj):
        """نام وظیفه مرتبط"""
        if obj.scheduled_task:
            return obj.scheduled_task.name
        elif obj.task_definition:
            return obj.task_definition.name
        return '-'
    task_name.short_description = 'وظیفه'
    
    def alert_type_badge(self, obj):
        """نمایش نوع هشدار"""
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
    alert_type_badge.short_description = 'نوع'
    
    def severity_badge(self, obj):
        """نمایش شدت"""
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
    severity_badge.short_description = 'شدت'
    
    def is_resolved_badge(self, obj):
        """وضعیت حل"""
        if obj.is_resolved:
            return format_html('<span style="color: green;">✓ حل شده</span>')
        return format_html('<span style="color: red;">✗ حل نشده</span>')
    is_resolved_badge.short_description = 'وضعیت'
    
    def resolve_alerts(self, request, queryset):
        """حل کردن هشدارها"""
        count = queryset.filter(is_resolved=False).update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolved_by=request.user,
            resolution_note='حل شده توسط ادمین'
        )
        self.message_user(request, f'{count} هشدار حل شد.')
    resolve_alerts.short_description = 'حل کردن هشدارهای انتخاب شده'
    
    def send_notifications(self, request, queryset):
        """ارسال اطلاع‌رسانی"""
        from .tasks import send_task_alerts
        send_task_alerts.delay()
        self.message_user(request, 'درخواست ارسال اطلاع‌رسانی ثبت شد.')
    send_notifications.short_description = 'ارسال اطلاع‌رسانی برای هشدارها'