"""
Serializers برای اپلیکیشن integrations
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from integrations.models import (
    IntegrationProvider,
    IntegrationCredential,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
    RateLimitRule
)

User = get_user_model()


class IntegrationProviderSerializer(serializers.ModelSerializer):
    """
    Serializer برای ارائه‌دهندگان خدمات یکپارچه‌سازی
    """
    credentials_count = serializers.SerializerMethodField()
    logs_count = serializers.SerializerMethodField()
    
    class Meta:
        model = IntegrationProvider
        fields = [
            'id', 'name', 'slug', 'provider_type', 'status',
            'description', 'api_base_url', 'documentation_url',
            'credentials_count', 'logs_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_credentials_count(self, obj):
        """تعداد credentials فعال"""
        return obj.credentials.filter(is_active=True).count()
    
    def get_logs_count(self, obj):
        """تعداد لاگ‌های 24 ساعت اخیر"""
        from django.utils import timezone
        from datetime import timedelta
        
        start_time = timezone.now() - timedelta(hours=24)
        return obj.logs.filter(created_at__gte=start_time).count()


class IntegrationCredentialSerializer(serializers.ModelSerializer):
    """
    Serializer برای اطلاعات احراز هویت
    """
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    is_valid = serializers.SerializerMethodField()
    masked_value = serializers.SerializerMethodField()
    
    class Meta:
        model = IntegrationCredential
        fields = [
            'id', 'provider', 'provider_name', 'key_name',
            'key_value', 'masked_value', 'is_encrypted',
            'environment', 'is_active', 'is_valid',
            'expires_at', 'created_at', 'updated_at',
            'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
        extra_kwargs = {
            'key_value': {'write_only': True}  # مقدار واقعی فقط در نوشتن
        }
    
    def get_is_valid(self, obj):
        """بررسی اعتبار"""
        return obj.is_valid()
    
    def get_masked_value(self, obj):
        """نمایش ماسک شده مقدار"""
        if obj.key_value:
            # نمایش 4 کاراکتر اول و آخر
            value = obj.key_value
            if len(value) > 8:
                return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            else:
                return '*' * len(value)
        return ''
    
    def create(self, validated_data):
        """ایجاد credential با ثبت کاربر ایجادکننده"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class IntegrationLogSerializer(serializers.ModelSerializer):
    """
    Serializer برای لاگ‌های یکپارچه‌سازی
    """
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    user_name = serializers.SerializerMethodField()
    
    class Meta:
        model = IntegrationLog
        fields = [
            'id', 'provider', 'provider_name', 'log_level',
            'service_name', 'action', 'request_data',
            'response_data', 'error_message', 'status_code',
            'duration_ms', 'user', 'user_name', 'ip_address',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_user_name(self, obj):
        """نام کاربر"""
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None


class WebhookEndpointSerializer(serializers.ModelSerializer):
    """
    Serializer برای Webhook Endpoints
    """
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    events_count = serializers.SerializerMethodField()
    pending_events = serializers.SerializerMethodField()
    
    class Meta:
        model = WebhookEndpoint
        fields = [
            'id', 'provider', 'provider_name', 'name',
            'endpoint_url', 'secret_key', 'events',
            'is_active', 'retry_count', 'timeout_seconds',
            'events_count', 'pending_events',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'secret_key': {'write_only': True}  # کلید امنیتی فقط در نوشتن
        }
    
    def get_events_count(self, obj):
        """تعداد کل رویدادها"""
        return obj.events_received.count()
    
    def get_pending_events(self, obj):
        """تعداد رویدادهای در انتظار پردازش"""
        return obj.events_received.filter(is_processed=False).count()
    
    def validate_endpoint_url(self, value):
        """اعتبارسنجی آدرس endpoint"""
        # بررسی یکتا بودن
        if self.instance:
            # در حالت update
            if WebhookEndpoint.objects.exclude(
                pk=self.instance.pk
            ).filter(endpoint_url=value).exists():
                raise serializers.ValidationError(
                    "این آدرس endpoint قبلاً ثبت شده است."
                )
        else:
            # در حالت create
            if WebhookEndpoint.objects.filter(endpoint_url=value).exists():
                raise serializers.ValidationError(
                    "این آدرس endpoint قبلاً ثبت شده است."
                )
        
        return value


class WebhookEventSerializer(serializers.ModelSerializer):
    """
    Serializer برای رویدادهای Webhook
    """
    webhook_name = serializers.CharField(source='webhook.name', read_only=True)
    provider_name = serializers.CharField(source='webhook.provider.name', read_only=True)
    
    class Meta:
        model = WebhookEvent
        fields = [
            'id', 'webhook', 'webhook_name', 'provider_name',
            'event_type', 'payload', 'headers', 'signature',
            'is_valid', 'is_processed', 'processed_at',
            'error_message', 'retry_count', 'received_at'
        ]
        read_only_fields = [
            'id', 'received_at', 'is_valid', 'is_processed',
            'processed_at'
        ]


class RateLimitRuleSerializer(serializers.ModelSerializer):
    """
    Serializer برای قوانین محدودیت نرخ
    """
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    rate_description = serializers.SerializerMethodField()
    
    class Meta:
        model = RateLimitRule
        fields = [
            'id', 'provider', 'provider_name', 'name',
            'endpoint_pattern', 'max_requests',
            'time_window_seconds', 'scope', 'is_active',
            'rate_description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_rate_description(self, obj):
        """توضیح خوانا از محدودیت"""
        return f"{obj.max_requests} درخواست در {obj.time_window_seconds} ثانیه"
    
    def validate(self, attrs):
        """اعتبارسنجی کلی"""
        if attrs.get('max_requests', 0) <= 0:
            raise serializers.ValidationError(
                "حداکثر درخواست باید بزرگتر از صفر باشد."
            )
        
        if attrs.get('time_window_seconds', 0) <= 0:
            raise serializers.ValidationError(
                "بازه زمانی باید بزرگتر از صفر باشد."
            )
        
        return attrs


# Serializers برای عملیات‌های خاص

class SendSMSSerializer(serializers.Serializer):
    """
    Serializer برای ارسال پیامک
    """
    receptor = serializers.CharField(
        max_length=11,
        min_length=11,
        help_text="شماره موبایل گیرنده (09123456789)"
    )
    message_type = serializers.ChoiceField(
        choices=['otp', 'pattern', 'simple'],
        default='simple'
    )
    template = serializers.CharField(
        max_length=100,
        required=False,
        help_text="نام قالب (برای otp و pattern)"
    )
    token = serializers.CharField(
        max_length=10,
        required=False,
        help_text="کد OTP"
    )
    tokens = serializers.DictField(
        required=False,
        help_text="توکن‌ها برای قالب"
    )
    message = serializers.CharField(
        max_length=1000,
        required=False,
        help_text="متن پیام (برای پیام ساده)"
    )
    
    def validate_receptor(self, value):
        """اعتبارسنجی شماره موبایل"""
        if not value.startswith('09') or not value[1:].isdigit():
            raise serializers.ValidationError(
                "شماره موبایل باید با 09 شروع شود و 11 رقم باشد."
            )
        return value
    
    def validate(self, attrs):
        """اعتبارسنجی کلی"""
        message_type = attrs.get('message_type')
        
        if message_type == 'otp' and not attrs.get('token'):
            raise serializers.ValidationError(
                "برای ارسال OTP، فیلد token الزامی است."
            )
        
        if message_type == 'pattern' and not attrs.get('tokens'):
            raise serializers.ValidationError(
                "برای ارسال با قالب، فیلد tokens الزامی است."
            )
        
        if message_type == 'simple' and not attrs.get('message'):
            raise serializers.ValidationError(
                "برای ارسال پیام ساده، فیلد message الزامی است."
            )
        
        return attrs


class AIGenerateSerializer(serializers.Serializer):
    """
    Serializer برای تولید متن با AI
    """
    prompt = serializers.CharField(
        max_length=5000,
        help_text="متن ورودی"
    )
    model = serializers.CharField(
        max_length=50,
        required=False,
        help_text="مدل AI (اختیاری)"
    )
    max_tokens = serializers.IntegerField(
        default=1000,
        min_value=1,
        max_value=4000,
        help_text="حداکثر توکن‌های خروجی"
    )
    temperature = serializers.FloatField(
        default=0.7,
        min_value=0,
        max_value=2,
        help_text="میزان خلاقیت (0-2)"
    )
    system_prompt = serializers.CharField(
        max_length=1000,
        required=False,
        help_text="پرامپت سیستم"
    )
    analysis_type = serializers.ChoiceField(
        choices=['general', 'symptoms', 'diagnosis', 'prescription'],
        default='general',
        required=False,
        help_text="نوع تحلیل پزشکی"
    )
    patient_context = serializers.DictField(
        required=False,
        help_text="اطلاعات بیمار"
    )


class WebhookProcessSerializer(serializers.Serializer):
    """
    Serializer برای پردازش webhook
    """
    endpoint_url = serializers.CharField(
        max_length=255,
        help_text="آدرس endpoint"
    )
    headers = serializers.DictField(
        help_text="هدرهای درخواست"
    )
    payload = serializers.DictField(
        help_text="محتوای درخواست"
    )
    signature = serializers.CharField(
        max_length=255,
        required=False,
        help_text="امضای webhook"
    )