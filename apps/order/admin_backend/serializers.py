# apps/order/admin_backend/serializers.py
from rest_framework import serializers
from apps.order.models.order import OrderStatus

class AdminOrderStatusTransitionSerializer(serializers.Serializer):
    new_status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")

class AdminOrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="Cancelled by administrator.")
