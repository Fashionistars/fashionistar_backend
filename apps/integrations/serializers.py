"""
Integrations Serializers for Fashionistar.
"""

from typing import Optional
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    IntegrationProvider,
    IntegrationCredential,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
    RateLimitRule
)

User = get_user_model()


class IntegrationProviderSerializer(serializers.ModelSerializer):
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
    
    def get_credentials_count(self, obj) -> int:
        return obj.credentials.filter(is_active=True).count()
    
    def get_logs_count(self, obj) -> int:
        from django.utils import timezone
        from datetime import timedelta
        start_time = timezone.now() - timedelta(hours=24)
        return obj.logs.filter(created_at__gte=start_time).count()


class IntegrationCredentialSerializer(serializers.ModelSerializer):
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
            'key_value': {'write_only': True}
        }
    
    def get_is_valid(self, obj) -> bool:
        return obj.is_valid()
    
    def get_masked_value(self, obj) -> str:
        if obj.key_value:
            value = obj.key_value
            if len(value) > 8:
                return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            else:
                return '*' * len(value)
        return ''
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class IntegrationLogSerializer(serializers.ModelSerializer):
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
    
    def get_user_name(self, obj) -> Optional[str]:
        if obj.user:
            return obj.user.get_full_name() or obj.user.phone_number
        return None


class WebhookEndpointSerializer(serializers.ModelSerializer):
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
            'secret_key': {'write_only': True}
        }
    
    def get_events_count(self, obj) -> int:
        return obj.events_received.count()
    
    def get_pending_events(self, obj) -> int:
        return obj.events_received.filter(is_processed=False).count()
    
    def validate_endpoint_url(self, value: str) -> str:
        if self.instance:
            if WebhookEndpoint.objects.exclude(pk=self.instance.pk).filter(endpoint_url=value).exists():
                raise serializers.ValidationError("This endpoint URL is already registered.")
        else:
            if WebhookEndpoint.objects.filter(endpoint_url=value).exists():
                raise serializers.ValidationError("This endpoint URL is already registered.")
        return value


class WebhookEventSerializer(serializers.ModelSerializer):
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
    
    def get_rate_description(self, obj) -> str:
        return f"{obj.max_requests} requests in {obj.time_window_seconds} seconds"
    
    def validate(self, attrs):
        if attrs.get('max_requests', 0) <= 0:
            raise serializers.ValidationError("Max requests must be greater than zero.")
        if attrs.get('time_window_seconds', 0) <= 0:
            raise serializers.ValidationError("Time window must be greater than zero.")
        return attrs


class SendSMSSerializer(serializers.Serializer):
    receptor = serializers.CharField(
        max_length=15,
        min_length=10,
        help_text="Recipient phone number"
    )
    message_type = serializers.ChoiceField(
        choices=['otp', 'pattern', 'simple'],
        default='simple'
    )
    template = serializers.CharField(
        max_length=100,
        required=False,
        help_text="Template name for OTP and pattern"
    )
    token = serializers.CharField(
        max_length=10,
        required=False,
        help_text="OTP verification token"
    )
    tokens = serializers.DictField(
        required=False,
        help_text="Custom pattern tokens map"
    )
    message = serializers.CharField(
        max_length=1000,
        required=False,
        help_text="Text content for simple messages"
    )
    
    def validate_receptor(self, value: str) -> str:
        if not value.isdigit():
            raise serializers.ValidationError("Recipient phone number must contain digits only.")
        return value
    
    def validate(self, attrs):
        message_type = attrs.get('message_type')
        if message_type == 'otp' and not attrs.get('token'):
            raise serializers.ValidationError("Token field is required for OTP messages.")
        if message_type == 'pattern' and not attrs.get('tokens'):
            raise serializers.ValidationError("Tokens field is required for pattern-based messages.")
        if message_type == 'simple' and not attrs.get('message'):
            raise serializers.ValidationError("Message content is required for simple messages.")
        return attrs


class AIGenerateSerializer(serializers.Serializer):
    prompt = serializers.CharField(
        max_length=5000,
        help_text="Input query"
    )
    model = serializers.CharField(
        max_length=50,
        required=False,
        help_text="Target AI model"
    )
    max_tokens = serializers.IntegerField(
        default=1000,
        min_value=1,
        max_value=4000,
        help_text="Maximum output tokens limit"
    )
    temperature = serializers.FloatField(
        default=0.7,
        min_value=0.0,
        max_value=2.0,
        help_text="Creativity scale"
    )
    system_prompt = serializers.CharField(
        max_length=1000,
        required=False,
        help_text="System instructions"
    )
    analysis_type = serializers.ChoiceField(
        choices=['general', 'sizing', 'styling', 'catalog'],
        default='general',
        required=False,
        help_text="Fashion query analysis type"
    )
    client_context = serializers.DictField(
        required=False,
        help_text="Client height, size, and styling preferences"
    )


class WebhookProcessSerializer(serializers.Serializer):
    endpoint_url = serializers.CharField(
        max_length=255,
        help_text="Endpoint URL slug"
    )
    headers = serializers.DictField(
        help_text="Request HTTP headers"
    )
    payload = serializers.DictField(
        help_text="Webhook payload body"
    )
    signature = serializers.CharField(
        max_length=255,
        required=False,
        help_text="Webhook validation signature"
    )