# apps/notification/admin_backend/serializers.py
from rest_framework import serializers

class AdminBroadcastNotificationSerializer(serializers.Serializer):
    notification_type = serializers.CharField(max_length=60)
    title = serializers.CharField(max_length=300)
    body = serializers.CharField()
    target_role = serializers.CharField(max_length=20, required=False, allow_null=True)
