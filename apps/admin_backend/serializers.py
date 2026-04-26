from rest_framework import serializers


class AdminProfitSerializer(serializers.Serializer):
    profit = serializers.DecimalField(max_digits=10, decimal_places=2)


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    delivery_status = serializers.CharField(max_length=100, required=False)
    tracking_id = serializers.CharField(max_length=255, required=False)

    def validate_delivery_status(self, value):
        valid_statuses = ["pending", "shipping", "delivered", "cancelled"]
        if value and value.lower() not in valid_statuses:
            raise serializers.ValidationError(
                f"Invalid delivery status. Must be one of: {', '.join(valid_statuses)}"
            )
        return value.lower()
