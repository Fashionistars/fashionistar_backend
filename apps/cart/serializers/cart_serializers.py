# apps/cart/serializers/cart_serializers.py
"""
Cart serializers.

CartItemSerializer — read (with product snapshot).
CartItemWriteSerializer — write (add/update).
CartSerializer — full cart with items, totals, coupon.
"""

from decimal import Decimal
from rest_framework import serializers

from apps.cart.models import Cart, CartItem
from apps.product.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    variant_name = serializers.SerializerMethodField()
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = CartItem
        fields = [
            "id", "product", "variant", "variant_name",
            "quantity", "unit_price", "line_total",
            "is_saved_for_later", "created_at",
        ]

    def get_variant_name(self, obj):
        return str(obj.variant) if obj.variant else None


class CartItemWriteSerializer(serializers.Serializer):
    product_slug = serializers.SlugField(write_only=True)
    variant_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=100)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, source="items.filter_active", read_only=True)
    saved_for_later = CartItemSerializer(many=True, source="items.filter_saved", read_only=True)
    subtotal = serializers.ReadOnlyField()
    coupon_discount = serializers.ReadOnlyField()
    total = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()
    coupon_code = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id", "items", "saved_for_later",
            "subtotal", "coupon_discount", "total", "item_count",
            "coupon_code", "last_activity",
        ]

    def get_coupon_code(self, obj):
        return obj.coupon.code if obj.coupon else None

    def to_representation(self, instance):
        # Override to use proper queryset methods
        rep = super().to_representation(instance)
        active_items = instance.items.filter(is_saved_for_later=False)
        saved_items = instance.items.filter(is_saved_for_later=True)
        rep["items"] = CartItemSerializer(active_items, many=True).data
        rep["saved_for_later"] = CartItemSerializer(saved_items, many=True).data
        return rep
