# apps/custom_order/admin_backend/serializers.py
from rest_framework import serializers

class AdminCustomOrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=20)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
