# apps/providers/admin_backend/serializers.py
from rest_framework import serializers

class EmailProviderConfigUpdateSerializer(serializers.Serializer):
    email_backend = serializers.CharField(max_length=255, required=False)
    sender_email = serializers.EmailField(required=False)
    api_key = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    api_secret = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    extra_config = serializers.JSONField(required=False, allow_null=True)

class SMSProviderConfigUpdateSerializer(serializers.Serializer):
    sms_backend = serializers.CharField(max_length=255, required=False)
    sender_id = serializers.CharField(max_length=50, required=False)
    api_key = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    api_secret = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    extra_config = serializers.JSONField(required=False, allow_null=True)

class KYCProviderConfigUpdateSerializer(serializers.Serializer):
    provider_slug = serializers.CharField(max_length=50, required=False)
    sandbox_mode = serializers.BooleanField(required=False)
    api_key = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    api_secret = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    webhook_secret = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    base_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    webhook_idempotency_ttl_seconds = serializers.IntegerField(required=False)
    extra_config = serializers.JSONField(required=False, allow_null=True)

class CloudinaryProviderConfigUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    upload_preset_images = serializers.CharField(max_length=100, required=False)
    upload_preset_videos = serializers.CharField(max_length=100, required=False)
    signature_ttl_seconds = serializers.IntegerField(required=False)
    max_image_bytes = serializers.IntegerField(required=False)
    max_video_bytes = serializers.IntegerField(required=False)

class MirrorSizeProviderConfigUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    product_name = serializers.CharField(max_length=100, required=False)
    browser_api_base_url = serializers.URLField(max_length=500, required=False)
    user_home_base_url = serializers.URLField(max_length=500, required=False)
    access_code_ttl_seconds = serializers.IntegerField(required=False)
