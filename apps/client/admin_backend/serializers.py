# apps/client/admin_backend/serializers.py
from rest_framework import serializers
from apps.client.models.client_profile import ClientProfile

class AdminClientProfileUpdateSerializer(serializers.Serializer):
    bio = serializers.CharField(required=False, allow_blank=True, max_length=500)
    state = serializers.CharField(required=False, allow_blank=True, max_length=100)
    country = serializers.CharField(required=False, allow_blank=True, max_length=100)
    preferred_size = serializers.ChoiceField(choices=ClientProfile.SIZE_CHOICES, required=False, allow_blank=True)
    email_notifications_enabled = serializers.BooleanField(required=False)
    sms_notifications_enabled = serializers.BooleanField(required=False)
