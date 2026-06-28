"""
تنظیمات پنل ادمین برای مدل‌های Analytics
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    """
    تنظیمات پنل ادمین برای مدل Metric
    """
    list_display = ['name', 'metric_type', 'value', 'timestamp']
    list_filter = ['metric_type', 'timestamp']
    search_fields = ['name']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('name', 'metric_type', 'value')
        }),
        ('اطلاعات اضافی', {
            'fields': ('tags', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    """
    تنظیمات پنل ادمین برای مدل UserActivity
    """
    list_display = ['user', 'action', 'resource', 'resource_id', 'timestamp']
    list_filter = ['action', 'resource', 'timestamp']
    search_fields = ['user__username', 'action', 'resource']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('user', 'action', 'resource', 'resource_id')
        }),
        ('اطلاعات جلسه', {
            'fields': ('ip_address', 'user_agent', 'session_id'),
            'classes': ('collapse',)
        }),
        ('اطلاعات اضافی', {
            'fields': ('metadata', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    """
    تنظیمات پنل ادمین برای مدل PerformanceMetric
    """
    list_display = ['endpoint', 'method', 'response_time_ms', 'status_code_colored', 'user', 'timestamp']
    list_filter = ['method', 'status_code', 'timestamp']
    search_fields = ['endpoint', 'user__username']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def status_code_colored(self, obj):
        """
        نمایش کد وضعیت با رنگ‌بندی
        """
        if obj.status_code >= 500:
            color = 'red'
        elif obj.status_code >= 400:
            color = 'orange'
        elif obj.status_code >= 300:
            color = 'yellow'
        else:
            color = 'green'
        
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.status_code
        )
    status_code_colored.short_description = 'کد وضعیت'
    
    fieldsets = (
        ('اطلاعات درخواست', {
            'fields': ('endpoint', 'method', 'user')
        }),
        ('اطلاعات عملکرد', {
            'fields': ('response_time_ms', 'status_code', 'error_message')
        }),
        ('اطلاعات اضافی', {
            'fields': ('metadata', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BusinessMetric)
class BusinessMetricAdmin(admin.ModelAdmin):
    """
    تنظیمات پنل ادمین برای مدل BusinessMetric
    """
    list_display = ['metric_name', 'value', 'period_start', 'period_end', 'created_at']
    list_filter = ['metric_name', 'created_at']
    search_fields = ['metric_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('اطلاعات متریک', {
            'fields': ('metric_name', 'value')
        }),
        ('دوره زمانی', {
            'fields': ('period_start', 'period_end')
        }),
        ('اطلاعات اضافی', {
            'fields': ('metadata', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """
    تنظیمات پنل ادمین برای مدل AlertRule
    """
    list_display = ['name', 'metric_name', 'operator', 'threshold', 'severity', 'is_active']
    list_filter = ['severity', 'is_active', 'operator']
    search_fields = ['name', 'metric_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('شرایط هشدار', {
            'fields': ('metric_name', 'operator', 'threshold', 'severity')
        }),
        ('اطلاعات سیستم', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """
    تنظیمات پنل ادمین برای مدل Alert
    """
    list_display = ['rule', 'status_colored', 'metric_value', 'fired_at', 'resolved_at']
    list_filter = ['status', 'rule__severity', 'fired_at']
    search_fields = ['rule__name', 'message']
    readonly_fields = ['fired_at']
    ordering = ['-fired_at']
    
    def status_colored(self, obj):
        """
        نمایش وضعیت با رنگ‌بندی
        """
        colors = {
            'firing': 'red',
            'resolved': 'green',
            'suppressed': 'orange'
        }
        color = colors.get(obj.status, 'black')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'وضعیت'
    
    fieldsets = (
        ('اطلاعات هشدار', {
            'fields': ('rule', 'status', 'message')
        }),
        ('جزئیات', {
            'fields': ('metric_value', 'fired_at', 'resolved_at')
        }),
        ('اطلاعات اضافی', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['resolve_alerts']
    
    def resolve_alerts(self, request, queryset):
        """
        عمل دسته‌ای برای حل هشدارها
        """
        from django.utils import timezone
        
        updated = queryset.filter(status='firing').update(
            status='resolved',
            resolved_at=timezone.now()
        )
        
        self.message_user(
            request,
            f'{updated} هشدار حل شد.'
        )
    resolve_alerts.short_description = 'حل هشدارهای انتخاب شده'