# apps/kyc/admin_backend/serializers.py
"""DRF write serializers for KYC admin mutations."""
from rest_framework import serializers


class AdminKYCApproveSerializer(serializers.Serializer):
    legal_name = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AdminKYCRejectSerializer(serializers.Serializer):
    notes = serializers.CharField(min_length=5, max_length=1000)
    allow_resubmit = serializers.BooleanField(default=True)
