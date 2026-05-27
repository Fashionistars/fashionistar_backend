# apps/vendor/admin_backend/serializers.py
"""DRF write serializers for vendor admin mutations."""

from __future__ import annotations
from decimal import Decimal
from rest_framework import serializers


class AdminVendorUpdateSerializer(serializers.Serializer):
    """Partial update for editable vendor fields."""
    store_name = serializers.CharField(max_length=150, required=False)
    tagline = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_featured = serializers.BooleanField(required=False)


class AdminVendorSuspendSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=500)


class AdminVendorRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=500)


class AdminVendorCommissionSerializer(serializers.Serializer):
    commission_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2,
        min_value=Decimal("0"), max_value=Decimal("100"),
    )
