# apps/product/serializers/coupon_serializers.py
from rest_framework import serializers
from apps.product.models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    is_valid = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id", "code", "discount_type", "discount_value",
            "minimum_order", "maximum_discount",
            "usage_limit", "usage_count",
            "active", "valid_from", "valid_to", "is_valid",
        ]
        read_only_fields = ["usage_count", "is_valid"]

    def get_is_valid(self, obj):
        return obj.is_valid()


class CouponWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "code", "discount_type", "discount_value",
            "minimum_order", "maximum_discount",
            "usage_limit", "active", "valid_from", "valid_to", "product",
        ]

    def validate(self, attrs):
        if attrs.get("valid_to") and attrs.get("valid_from"):
            if attrs["valid_to"] <= attrs["valid_from"]:
                raise serializers.ValidationError("valid_to must be after valid_from.")
        return attrs
