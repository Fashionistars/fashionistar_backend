# apps/order/serializers/order_serializers.py
from rest_framework import serializers
from apps.order.models import Order, OrderItem, OrderStatusHistory


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id", "product", "variant",
            "product_title", "product_sku", "variant_description",
            "unit_price", "quantity", "commission_rate", "commission_amount",
            "line_total", "is_custom_order",
        ]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "note", "created_at"]


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()
    vendor_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "fulfillment_type",
            "total_amount", "currency", "item_count",
            "vendor_name", "paid_at", "created_at",
        ]

    def get_item_count(self, obj):
        return obj.items.count()

    def get_vendor_name(self, obj):
        if obj.vendor:
            return getattr(obj.vendor, "business_name", str(obj.vendor))
        return None


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "fulfillment_type",
            "subtotal", "shipping_amount", "discount_amount",
            "total_amount", "commission_amount", "vendor_payout", "currency",
            "payment_reference", "payment_gateway", "paid_at",
            "coupon_code", "delivery_address",
            "tracking_number", "estimated_delivery",
            "measurement_profile_id", "notes",
            "escrow_released", "is_test_order",
            "items", "status_history",
            "created_at", "updated_at",
        ]


class PlaceOrderSerializer(serializers.Serializer):
    delivery_address = serializers.DictField(child=serializers.CharField(), required=True)
    fulfillment_type = serializers.ChoiceField(
        choices=["delivery", "pickup", "digital", "custom"],
        default="delivery",
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
    measurement_profile_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_delivery_address(self, value):
        if not value.get("address_line_1") or not value.get("city"):
            raise serializers.ValidationError("delivery_address must include address_line_1 and city.")
        return value


class TransitionStatusSerializer(serializers.Serializer):
    new_status = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True)
