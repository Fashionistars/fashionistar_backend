"""
Admin interface برای اپلیکیشن integrations
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from integrations.models import (
    IntegrationProvider,
    IntegrationCredential,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
    RateLimitRule
)


@admin.register(IntegrationProvider)
class IntegrationProviderAdmin(admin.ModelAdmin):
    """
    ادمین برای ارائه‌دهندگان خدمات یکپارچه‌سازی
    """
    list_display = [
        'name', 'slug', 'provider_type', 'status_badge',
        'credentials_count', 'webhooks_count', 'created_at'
    ]
    list_filter = ['provider_type', 'status', 'created_at']
    search_fields = ['name', 'slug', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'name', 'slug', 'provider_type', 'status')
        }),
        ('تنظیمات API', {
            'fields': ('api_base_url', 'documentation_url')
        }),
        ('توضیحات', {
            'fields': ('description',)
        }),
        ('تاریخ‌ها', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def status_badge(self, obj):
        """نمایش وضعیت با رنگ"""
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
    status_badge.short_description = 'وضعیت'
    
    def credentials_count(self, obj):
        """تعداد credentials"""
        count = obj.credentials.filter(is_active=True).count()
        url = reverse('admin:integrations_integrationcredential_changelist')
        return format_html(
            '<a href="{}?provider__id__exact={}">{} فعال</a>',
            url, obj.id, count
        )
    credentials_count.short_description = 'اطلاعات احراز هویت'
    
    def webhooks_count(self, obj):
        """تعداد webhooks"""
        count = obj.webhooks.count()
        url = reverse('admin:integrations_webhookendpoint_changelist')
        return format_html(
            '<a href="{}?provider__id__exact={}">{}</a>',
            url, obj.id, count
        )
    webhooks_count.short_description = 'Webhooks'


@admin.register(IntegrationCredential)
class IntegrationCredentialAdmin(admin.ModelAdmin):
    """
    ادمین برای اطلاعات احراز هویت
    """
    list_display = [
        'provider', 'key_name', 'environment', 'is_active',
        'is_valid_badge', 'expires_at', 'created_by'
    ]
    list_filter = ['provider', 'environment', 'is_active', 'is_encrypted']
    search_fields = ['key_name', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'provider', 'key_name', 'key_value')
        }),
        ('تنظیمات', {
            'fields': ('environment', 'is_encrypted', 'is_active', 'expires_at')
        }),
        ('اطلاعات ایجاد', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def is_valid_badge(self, obj):
        """نمایش اعتبار با رنگ"""
        if obj.is_valid():
            return format_html(
                '<span style="color: green;">✓</span> معتبر'
            )
        else:
            return format_html(
                '<span style="color: red;">✗</span> نامعتبر'
            )
    is_valid_badge.short_description = 'اعتبار'
    
    def save_model(self, request, obj, form, change):
        """ثبت کاربر ایجادکننده"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(IntegrationLog)
class IntegrationLogAdmin(admin.ModelAdmin):
    """
    ادمین برای لاگ‌های یکپارچه‌سازی
    """
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
        ('اطلاعات اصلی', {
            'fields': (
                'id', 'provider', 'log_level', 'service_name',
                'action', 'created_at'
            )
        }),
        ('جزئیات درخواست', {
            'fields': (
                'request_data_formatted', 'response_data_formatted',
                'status_code', 'duration_ms'
            ),
            'classes': ('collapse',)
        }),
        ('خطا', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('اطلاعات کاربر', {
            'fields': ('user', 'ip_address'),
            'classes': ('collapse',)
        })
    )
    
    def log_level_badge(self, obj):
        """نمایش سطح لاگ با رنگ"""
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
    log_level_badge.short_description = 'سطح'
    
    def request_data_formatted(self, obj):
        """نمایش فرمت شده داده‌های درخواست"""
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.request_data, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.request_data)
    request_data_formatted.short_description = 'داده‌های درخواست'
    
    def response_data_formatted(self, obj):
        """نمایش فرمت شده داده‌های پاسخ"""
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.response_data, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.response_data)
    response_data_formatted.short_description = 'داده‌های پاسخ'
    
    def has_add_permission(self, request):
        """غیرفعال کردن افزودن دستی"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """غیرفعال کردن ویرایش"""
        return False


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    """
    ادمین برای Webhook Endpoints
    """
    list_display = [
        'name', 'provider', 'endpoint_url', 'is_active',
        'events_count', 'pending_events', 'created_at'
    ]
    list_filter = ['provider', 'is_active', 'created_at']
    search_fields = ['name', 'endpoint_url', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    filter_horizontal = []
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'provider', 'name', 'endpoint_url')
        }),
        ('امنیت', {
            'fields': ('secret_key',),
            'classes': ('collapse',)
        }),
        ('تنظیمات', {
            'fields': ('events', 'is_active', 'retry_count', 'timeout_seconds')
        }),
        ('تاریخ‌ها', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """افزودن annotation ها"""
        qs = super().get_queryset(request)
        return qs.annotate(
            _events_count=Count('events_received'),
            _pending_count=Count(
                'events_received',
                filter=models.Q(events_received__is_processed=False)
            )
        )
    
    def events_count(self, obj):
        """تعداد کل رویدادها"""
        count = getattr(obj, '_events_count', 0)
        url = reverse('admin:integrations_webhookevent_changelist')
        return format_html(
            '<a href="{}?webhook__id__exact={}">{}</a>',
            url, obj.id, count
        )
    events_count.short_description = 'رویدادها'
    events_count.admin_order_field = '_events_count'
    
    def pending_events(self, obj):
        """تعداد رویدادهای در انتظار"""
        count = getattr(obj, '_pending_count', 0)
        if count > 0:
            return format_html(
                '<span style="color: orange;">{} در انتظار</span>',
                count
            )
        return '0'
    pending_events.short_description = 'در انتظار'
    pending_events.admin_order_field = '_pending_count'


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    """
    ادمین برای رویدادهای Webhook
    """
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
        ('اطلاعات رویداد', {
            'fields': (
                'id', 'webhook', 'event_type', 'received_at'
            )
        }),
        ('محتوا', {
            'fields': (
                'payload_formatted', 'headers_formatted', 'signature'
            ),
            'classes': ('collapse',)
        }),
        ('وضعیت پردازش', {
            'fields': (
                'is_valid', 'is_processed', 'processed_at',
                'retry_count', 'error_message'
            )
        })
    )
    
    def is_valid_badge(self, obj):
        """نمایش اعتبار با رنگ"""
        if obj.is_valid:
            return format_html('<span style="color: green;">✓</span>')
        else:
            return format_html('<span style="color: red;">✗</span>')
    is_valid_badge.short_description = 'معتبر'
    
    def is_processed_badge(self, obj):
        """نمایش وضعیت پردازش با رنگ"""
        if obj.is_processed:
            return format_html('<span style="color: green;">✓</span>')
        else:
            return format_html('<span style="color: orange;">⏳</span>')
    is_processed_badge.short_description = 'پردازش'
    
    def payload_formatted(self, obj):
        """نمایش فرمت شده payload"""
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.payload, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.payload)
    payload_formatted.short_description = 'محتوا'
    
    def headers_formatted(self, obj):
        """نمایش فرمت شده headers"""
        import json
        try:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.headers, indent=2, ensure_ascii=False)
            )
        except:
            return str(obj.headers)
    headers_formatted.short_description = 'هدرها'
    
    def has_add_permission(self, request):
        """غیرفعال کردن افزودن دستی"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """غیرفعال کردن ویرایش"""
        return False


@admin.register(RateLimitRule)
class RateLimitRuleAdmin(admin.ModelAdmin):
    """
    ادمین برای قوانین محدودیت نرخ
    """
    list_display = [
        'name', 'provider', 'endpoint_pattern', 'rate_description',
        'scope', 'is_active', 'created_at'
    ]
    list_filter = ['provider', 'scope', 'is_active', 'created_at']
    search_fields = ['name', 'endpoint_pattern', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('id', 'provider', 'name', 'endpoint_pattern')
        }),
        ('محدودیت', {
            'fields': ('max_requests', 'time_window_seconds', 'scope')
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
        ('تاریخ‌ها', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def rate_description(self, obj):
        """توضیح خوانا از محدودیت"""
        return f"{obj.max_requests} درخواست در {obj.time_window_seconds} ثانیه"
    rate_description.short_description = 'محدودیت'


# تنظیمات عمومی ادمین
admin.site.site_header = "مدیریت یکپارچه‌سازی‌ها"
admin.site.site_title = "Integrations Admin"
admin.site.index_title = "داشبورد یکپارچه‌سازی‌ها"