# apps/measurements/admin_backend/serializers.py
from rest_framework import serializers

class AdminVerifyMeasurementSerializer(serializers.Serializer):
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
