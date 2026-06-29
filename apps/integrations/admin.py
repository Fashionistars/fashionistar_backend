"""
Admin interface for integrations app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .models import (
    IntegrationProvider,
    IntegrationCredential,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
    RateLimitRule
)


@admin.register(IntegrationProvider)
class IntegrationProviderAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'slug', 'provider_type', 'status_badge',
        'credentials_count', 'webhooks_count', 'created_at'
    ]
    list_filter = ['provider_type', 'status', 'created_at']
    search_fields = ['name', 'slug', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Main Info', {
            'fields': ('id', 'name', 'slug', 'provider_type', 'status')
        }),
        ('API Settings', {
            'fields': ('api_base_url', 'documentation_url')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def status_badge(self, obj):
        colors = {
            'active': 'green',
            'inactive': 'red',
            'maintenance': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {};">●</span> {}',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def credentials_count(self, obj):
        count = obj.credentials.filter(is_active=True).count()
        url = reverse('admin:integrations_integrationcredential_changelist')
        return format_html(
            '<a href="{}?provider__id__exact={}">{} Active</a>',
            url, obj.id, count
        )
    credentials_count.short_description = 'Credentials'
    
    def webhooks_count(self, obj):
        count = obj.webhooks.count()
        url = reverse('admin:integrations_webhookendpoint_changelist')
        return format_html(
            '<a href="{}?provider__id__exact={}">{}</a>',
            url, obj.id, count
        )
    webhooks_count.short_description = 'Webhooks'


@admin.register(IntegrationCredential)
class IntegrationCredentialAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'key_name', 'environment', 'is_active',
        'is_valid_badge', 'expires_at', 'created_by'
    ]
    list_filter = ['provider', 'environment', 'is_active', 'is_encrypted']
    search_fields = ['key_name', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Credentials Info', {
            'fields': ('id', 'provider', 'key_name', 'key_value')
        }),
        ('Settings', {
            'fields': ('environment', 'is_encrypted', 'is_active', 'expires_at')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def is_valid_badge(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">✓ Valid</span>')
        return format_html('<span style="color: red;">✗ Invalid</span>')
    is_valid_badge.short_description = 'Validity'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(IntegrationLog)
class IntegrationLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'provider', 'log_level_badge', 'service_name',
        'action', 'status_code', 'duration_ms', 'user'
    ]
    list_filter = ['provider', 'log_level', 'service_name', 'created_at']
    search_fields = ['action', 'error_message', 'user__username']
    readonly_fields = [
        'id', 'provider', 'log_level', 'service_name', 'action',
        'request_data_formatted', 'response_data_formatted',
        'error_message', 'status_code', 'duration_ms',
        'user', 'ip_address', 'created_at'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Log Info', {
            'fields': (
                'id', 'provider', 'log_level', 'service_name',
                'action', 'created_at'
            )
        }),
        ('Payload Details', {
            'fields': (
                'request_data_formatted', 'response_data_formatted',
                'status_code', 'duration_ms'
            ),
            'classes': ('collapse',)
        }),
        ('Failure / Error', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('User Info', {
            'fields': ('user', 'ip_address'),
            'classes': ('collapse',)
        })
    )
    
    def log_level_badge(self, obj):
        colors = {
            'debug': 'gray',
            'info': 'blue',
            'warning': 'orange',
            'error': 'red',
            'critical': 'darkred'
        }
        color = colors.get(obj.log_level, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_log_level_display()
        )
    log_level_badge.short_description = 'Level'
    
    def request_data_formatted(self, obj):
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.request_data, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.request_data)
    request_data_formatted.short_description = 'Request Data'
    
    def response_data_formatted(self, obj):
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.response_data, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.response_data)
    response_data_formatted.short_description = 'Response Data'
    
    def has_add_permission(self, request) -> bool:
        return False
    
    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'provider', 'endpoint_url', 'is_active',
        'events_count', 'pending_events', 'created_at'
    ]
    list_filter = ['provider', 'is_active', 'created_at']
    search_fields = ['name', 'endpoint_url', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Main Info', {
            'fields': ('id', 'provider', 'name', 'endpoint_url')
        }),
        ('Security', {
            'fields': ('secret_key',),
            'classes': ('collapse',)
        }),
        ('Config', {
            'fields': ('events', 'is_active', 'retry_count', 'timeout_seconds')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _events_count=Count('events_received'),
            _pending_count=Count('events_received', filter=Count('events_received', filter=Count('events_received', filter=Count('events_received')))) # Note: simple filter annotation is better
        )
    
    def events_count(self, obj):
        count = obj.events_received.count()
        url = reverse('admin:integrations_webhookevent_changelist')
        return format_html(
            '<a href="{}?webhook__id__exact={}">{}</a>',
            url, obj.id, count
        )
    events_count.short_description = 'Events'
    
    def pending_events(self, obj):
        count = obj.events_received.filter(is_processed=False).count()
        if count > 0:
            return format_html('<span style="color: orange;">{} Pending</span>', count)
        return '0'
    pending_events.short_description = 'Pending'


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'received_at', 'webhook', 'event_type', 'is_valid_badge',
        'is_processed_badge', 'retry_count', 'processed_at'
    ]
    list_filter = [
        'webhook__provider', 'webhook', 'event_type',
        'is_valid', 'is_processed', 'received_at'
    ]
    search_fields = ['event_type', 'error_message', 'webhook__name']
    readonly_fields = [
        'id', 'webhook', 'event_type', 'payload_formatted',
        'headers_formatted', 'signature', 'is_valid',
        'is_processed', 'processed_at', 'error_message',
        'retry_count', 'received_at'
    ]
    date_hierarchy = 'received_at'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('id', 'webhook', 'event_type', 'received_at')
        }),
        ('Content', {
            'fields': ('payload_formatted', 'headers_formatted', 'signature'),
            'classes': ('collapse',)
        }),
        ('Processing Status', {
            'fields': (
                'is_valid', 'is_processed', 'processed_at',
                'retry_count', 'error_message'
            )
        })
    )
    
    def is_valid_badge(self, obj):
        if obj.is_valid:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    is_valid_badge.short_description = 'Valid'
    
    def is_processed_badge(self, obj):
        if obj.is_processed:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: orange;">⏳</span>')
    is_processed_badge.short_description = 'Processed'
    
    def payload_formatted(self, obj):
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.payload, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.payload)
    payload_formatted.short_description = 'Payload'
    
    def headers_formatted(self, obj):
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.headers, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.headers)
    headers_formatted.short_description = 'Headers'
    
    def has_add_permission(self, request) -> bool:
        return False
    
    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(RateLimitRule)
class RateLimitRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'provider', 'endpoint_pattern', 'rate_description',
        'scope', 'is_active', 'created_at'
    ]
    list_filter = ['provider', 'scope', 'is_active', 'created_at']
    search_fields = ['name', 'endpoint_pattern', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Main Info', {
            'fields': ('id', 'provider', 'name', 'endpoint_pattern')
        }),
        ('Rate Limits', {
            'fields': ('max_requests', 'time_window_seconds', 'scope')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def rate_description(self, obj) -> str:
        return f"{obj.max_requests} requests in {obj.time_window_seconds} seconds"
    rate_description.short_description = 'Limits'


# Admin Site Header Customization
admin.site.site_header = "Integrations Admin Portal"
admin.site.site_title = "Integrations Admin"
admin.site.index_title = "Integrations System Dashboard"