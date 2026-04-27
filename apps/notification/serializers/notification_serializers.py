# apps/notification/serializers/notification_serializers.py
"""
DRF serializers for the Notification domain.
"""
from rest_framework import serializers
from apps.notification.models import (
    Notification,
    NotificationChannel,
    NotificationType,
    NotificationPreference,
)


class NotificationSerializer(serializers.ModelSerializer):
    """Read-only serializer for rendering notification records to the client."""

    is_read = serializers.BooleanField(read_only=True)
    is_sent = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "channel",
            "title",
            "body",
            "metadata",
            "is_read",
            "is_sent",
            "read_at",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Read serializer for user notification preferences."""

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "notification_type",
            "channel",
            "enabled",
        ]
        read_only_fields = ["id"]


class NotificationPreferenceWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for updating a notification preference.
    The user is injected from the request — NOT accepted from payload.
    """

    notification_type = serializers.ChoiceField(choices=NotificationType.choices)
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)

    class Meta:
        model = NotificationPreference
        fields = ["notification_type", "channel", "enabled"]

    def validate(self, attrs):
        # Block disabling mandatory notification types
        from apps.notification.services.notification_service import _MANDATORY_TYPES
        if attrs["notification_type"] in _MANDATORY_TYPES and not attrs.get("enabled", True):
            raise serializers.ValidationError(
                f"Notification type '{attrs['notification_type']}' cannot be disabled. "
                "It is required for financial compliance."
            )
        return attrs
