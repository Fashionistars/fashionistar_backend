"""
Admin interface for analytics app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ['name', 'metric_type', 'value', 'timestamp']
    list_filter = ['metric_type', 'timestamp']
    search_fields = ['name']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    fieldsets = (
        ('Main Info', {
            'fields': ('name', 'metric_type', 'value')
        }),
        ('Metadata', {
            'fields': ('tags', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'resource', 'resource_id', 'timestamp']
    list_filter = ['action', 'resource', 'timestamp']
    search_fields = ['user__phone', 'user__email', 'action', 'resource']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    fieldsets = (
        ('Main Info', {
            'fields': ('user', 'action', 'resource', 'resource_id')
        }),
        ('Session Info', {
            'fields': ('ip_address', 'user_agent', 'session_id'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    list_display = ['endpoint', 'method', 'response_time_ms', 'status_code_colored', 'user', 'timestamp']
    list_filter = ['method', 'status_code', 'timestamp']
    search_fields = ['endpoint', 'user__phone', 'user__email']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def status_code_colored(self, obj):
        if obj.status_code >= 500:
            color = 'red'
        elif obj.status_code >= 400:
            color = 'orange'
        elif obj.status_code >= 300:
            color = 'gold'
        else:
            color = 'green'
        
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.status_code
        )
    status_code_colored.short_description = 'Status Code'
    
    fieldsets = (
        ('Request Details', {
            'fields': ('endpoint', 'method', 'user')
        }),
        ('Performance indicators', {
            'fields': ('response_time_ms', 'status_code', 'error_message')
        }),
        ('Metadata', {
            'fields': ('metadata', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BusinessMetric)
class BusinessMetricAdmin(admin.ModelAdmin):
    list_display = ['metric_name', 'value', 'period_start', 'period_end', 'created_at']
    list_filter = ['metric_name', 'created_at']
    search_fields = ['metric_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Metric Details', {
            'fields': ('metric_name', 'value')
        }),
        ('Interval', {
            'fields': ('period_start', 'period_end')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'metric_name', 'operator', 'threshold', 'severity', 'is_active']
    list_filter = ['severity', 'is_active', 'operator']
    search_fields = ['name', 'metric_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Main Info', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Alert Thresholds', {
            'fields': ('metric_name', 'operator', 'threshold', 'severity')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['rule', 'status_colored', 'metric_value', 'fired_at', 'resolved_at']
    list_filter = ['status', 'rule__severity', 'fired_at']
    search_fields = ['rule__name', 'message']
    readonly_fields = ['fired_at']
    ordering = ['-fired_at']
    
    def status_colored(self, obj):
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
    status_colored.short_description = 'Status'
    
    fieldsets = (
        ('Alert details', {
            'fields': ('rule', 'status', 'message')
        }),
        ('Metrics & Resolution', {
            'fields': ('metric_value', 'fired_at', 'resolved_at')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['resolve_alerts']
    
    def resolve_alerts(self, request, queryset):
        updated = queryset.filter(status='firing').update(
            status='resolved',
            resolved_at=timezone.now()
        )
        
        self.message_user(
            request,
            f'{updated} alerts resolved successfully.'
        )
    resolve_alerts.short_description = 'Mark selected alerts as resolved'