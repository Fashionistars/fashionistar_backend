"""
پنل مدیریت برای اپلیکیشن DevOps
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.db.models import Count, Q
from django.http import HttpResponse
import json

from .models import (
    EnvironmentConfig,
    SecretConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)


@admin.register(EnvironmentConfig)
class EnvironmentConfigAdmin(admin.ModelAdmin):
    """مدیریت تنظیمات محیط"""
    
    list_display = [
        'name', 'environment_type', 'is_active', 
        'secrets_count', 'deployments_count', 'created_at'
    ]
    list_filter = ['environment_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('name', 'environment_type', 'description', 'is_active')
        }),
        ('اطلاعات تکمیلی', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def secrets_count(self, obj):
        """تعداد secrets هر محیط"""
        count = obj.secrets.filter(is_active=True).count()
        return format_html(
            '<span style="color: {};">{}</span>',
            'green' if count > 0 else 'red',
            count
        )
    secrets_count.short_description = 'تعداد Secrets'
    
    def deployments_count(self, obj):
        """تعداد deployment های هر محیط"""
        count = obj.deployments.count()
        return format_html(
            '<a href="{}?environment__id__exact={}">{}</a>',
            reverse('admin:devops_deploymenthistory_changelist'),
            obj.id,
            count
        )
    deployments_count.short_description = 'تعداد Deployments'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            secrets_count=Count('secrets', filter=Q(secrets__is_active=True)),
            deployments_count=Count('deployments')
        )


@admin.register(SecretConfig)
class SecretConfigAdmin(admin.ModelAdmin):
    """مدیریت تنظیمات محرمانه"""
    
    list_display = [
        'key_name', 'environment', 'category', 'is_active', 
        'is_expired_display', 'created_at'
    ]
    list_filter = ['environment', 'category', 'is_active', 'created_at']
    search_fields = ['key_name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'is_expired_display']
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('environment', 'key_name', 'encrypted_value', 'category')
        }),
        ('تنظیمات پیشرفته', {
            'fields': ('description', 'is_active', 'expires_at'),
            'classes': ('collapse',)
        }),
        ('اطلاعات تکمیلی', {
            'fields': ('created_by', 'created_at', 'updated_at', 'is_expired_display'),
            'classes': ('collapse',)
        }),
    )
    
    def is_expired_display(self, obj):
        """نمایش وضعیت انقضا"""
        if obj.expires_at is None:
            return format_html('<span style="color: gray;">بدون انقضا</span>')
        
        if obj.is_expired:
            return format_html('<span style="color: red;">منقضی شده</span>')
        else:
            days_left = (obj.expires_at - timezone.now()).days
            color = 'orange' if days_left <= 7 else 'green'
            return format_html(
                '<span style="color: {};">{} روز مانده</span>',
                color,
                days_left
            )
    is_expired_display.short_description = 'وضعیت انقضا'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('environment')


@admin.register(DeploymentHistory)
class DeploymentHistoryAdmin(admin.ModelAdmin):
    """مدیریت تاریخچه deployments"""
    
    list_display = [
        'environment', 'version', 'status_display', 'branch',
        'deployed_by', 'duration_display', 'started_at'
    ]
    list_filter = ['environment', 'status', 'branch', 'started_at']
    search_fields = ['version', 'commit_hash', 'deployed_by__username']
    readonly_fields = [
        'started_at', 'completed_at', 'duration_display',
        'deployment_logs_display'
    ]
    fieldsets = (
        ('اطلاعات Deployment', {
            'fields': ('environment', 'version', 'commit_hash', 'branch', 'status')
        }),
        ('زمان‌بندی', {
            'fields': ('started_at', 'completed_at', 'duration_display')
        }),
        ('جزئیات', {
            'fields': (
                'deployed_by', 'artifacts_url', 'rollback_from',
                'deployment_logs_display'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def status_display(self, obj):
        """نمایش رنگی وضعیت"""
        colors = {
            'pending': 'orange',
            'running': 'blue',
            'success': 'green',
            'failed': 'red',
            'cancelled': 'gray',
            'rollback': 'purple',
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_display.short_description = 'وضعیت'
    
    def duration_display(self, obj):
        """نمایش مدت زمان deployment"""
        if obj.duration:
            return f"{obj.duration.total_seconds():.0f} ثانیه"
        return "نامشخص"
    duration_display.short_description = 'مدت زمان'
    
    def deployment_logs_display(self, obj):
        """نمایش لاگ‌های deployment"""
        if obj.deployment_logs:
            return format_html(
                '<pre style="max-height: 200px; overflow-y: scroll;">{}</pre>',
                obj.deployment_logs[:1000] + ('...' if len(obj.deployment_logs) > 1000 else '')
            )
        return "لاگی موجود نیست"
    deployment_logs_display.short_description = 'لاگ‌های Deployment'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'environment', 'deployed_by', 'rollback_from'
        )


@admin.register(HealthCheck)
class HealthCheckAdmin(admin.ModelAdmin):
    """مدیریت نتایج health check"""
    
    list_display = [
        'service_name', 'environment', 'status_display',
        'response_time_display', 'status_code', 'checked_at'
    ]
    list_filter = ['environment', 'status', 'service_name', 'checked_at']
    search_fields = ['service_name', 'endpoint_url', 'error_message']
    readonly_fields = ['checked_at', 'response_data_display']
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('environment', 'service_name', 'endpoint_url', 'status')
        }),
        ('نتایج بررسی', {
            'fields': (
                'response_time', 'status_code', 'error_message',
                'response_data_display', 'checked_at'
            )
        }),
    )
    
    def status_display(self, obj):
        """نمایش رنگی وضعیت سلامت"""
        colors = {
            'healthy': 'green',
            'warning': 'orange',
            'critical': 'red',
            'unknown': 'gray',
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_display.short_description = 'وضعیت'
    
    def response_time_display(self, obj):
        """نمایش زمان پاسخ"""
        if obj.response_time is not None:
            color = 'green' if obj.response_time < 1000 else 'orange' if obj.response_time < 5000 else 'red'
            return format_html(
                '<span style="color: {};">{:.0f} ms</span>',
                color,
                obj.response_time
            )
        return "نامشخص"
    response_time_display.short_description = 'زمان پاسخ'
    
    def response_data_display(self, obj):
        """نمایش داده‌های پاسخ"""
        if obj.response_data:
            return format_html(
                '<pre style="max-height: 150px; overflow-y: scroll;">{}</pre>',
                json.dumps(obj.response_data, indent=2, ensure_ascii=False)
            )
        return "داده‌ای موجود نیست"
    response_data_display.short_description = 'داده‌های پاسخ'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('environment')


@admin.register(ServiceMonitoring)
class ServiceMonitoringAdmin(admin.ModelAdmin):
    """مدیریت مانیتورینگ سرویس‌ها"""
    
    list_display = [
        'service_name', 'environment', 'service_type',
        'is_active', 'alert_on_failure', 'check_interval',
        'last_check_status', 'updated_at'
    ]
    list_filter = ['environment', 'service_type', 'is_active', 'alert_on_failure']
    search_fields = ['service_name', 'health_check_url']
    readonly_fields = ['created_at', 'updated_at', 'last_check_status']
    fieldsets = (
        ('اطلاعات سرویس', {
            'fields': ('environment', 'service_name', 'service_type', 'health_check_url')
        }),
        ('تنظیمات مانیتورینگ', {
            'fields': ('check_interval', 'timeout', 'is_active', 'alert_on_failure')
        }),
        ('اطلاعات تکمیلی', {
            'fields': ('created_at', 'updated_at', 'last_check_status'),
            'classes': ('collapse',)
        }),
    )
    
    def last_check_status(self, obj):
        """آخرین وضعیت بررسی"""
        latest_check = obj.environment.health_checks.filter(
            service_name=obj.service_name
        ).first()
        
        if latest_check:
            colors = {
                'healthy': 'green',
                'warning': 'orange',
                'critical': 'red',
                'unknown': 'gray',
            }
            return format_html(
                '<span style="color: {};">{} ({})</span>',
                colors.get(latest_check.status, 'black'),
                latest_check.get_status_display(),
                latest_check.checked_at.strftime('%H:%M')
            )
        return format_html('<span style="color: gray;">هنوز بررسی نشده</span>')
    last_check_status.short_description = 'آخرین بررسی'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('environment')