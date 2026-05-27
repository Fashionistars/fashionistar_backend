# apps/payment/admin_backend/serializers.py
from rest_framework import serializers

class AdminRefundPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
