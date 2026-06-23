# apps/order/serializers/order_serializers.py
from rest_framework import serializers
from apps.order.models import (
    Order,
    CartOrderItem,
    OrderStatusHistory,
    OrderPaymentRecord,
    OrderCommercialTransitionLog,
)

OrderItem = CartOrderItem  # alias for clarity in serializers below


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id", "product", "variant",
            "product_title_snapshot", "product_sku_snapshot", "variant_description_snapshot",
            "vendor_name_snapshot",
            "unit_price", "quantity", "commission_rate", "commission_amount",
            "line_total", "is_custom_order",
        ]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "note", "created_at"]


class OrderPaymentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderPaymentRecord
        fields = [
            "sequence_number",
            "payment_source",
            "provider",
            "selected_percent",
            "applied_percent",
            "amount",
            "currency",
            "cumulative_amount_paid",
            "cumulative_percent_paid",
            "remaining_amount",
            "remaining_percent",
            "is_final_payment",
            "paid_at",
            "correlation_id",
            "metadata",
        ]


class OrderCommercialTransitionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderCommercialTransitionLog
        fields = [
            "transition_type",
            "from_status",
            "to_status",
            "delivery_mode",
            "cash_payment_mode_snapshot",
            "selected_percent",
            "cumulative_percent_paid",
            "amount_delta",
            "balance_after",
            "actor_role",
            "occurred_at",
            "correlation_id",
            "note",
            "metadata",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()
    vendor_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "fulfillment_type",
            "total_amount", "currency", "item_count",
            "amount_paid_total", "percent_paid_total", "amount_outstanding",
            "is_fully_paid", "cash_payment_mode_snapshot", "delivery_mode",
            "vendor_name", "paid_at", "created_at",
        ]

    def get_item_count(self, obj):
        return obj.cart_order_items.count()

    def get_vendor_name(self, obj):
        if obj.vendor:
            return getattr(obj.vendor, "business_name", str(obj.vendor))
        return None


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(source="cart_order_items", many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(source="order_status_history", many=True, read_only=True)
    payment_records = OrderPaymentRecordSerializer(many=True, read_only=True)
    commercial_transition_logs = OrderCommercialTransitionLogSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "fulfillment_type",
            "subtotal", "shipping_amount", "discount_amount",
            "total_amount", "commission_amount", "vendor_payout", "currency",
            "payment_reference", "payment_gateway", "paid_at",
            "amount_paid_total", "percent_paid_total", "amount_outstanding",
            "is_fully_paid", "first_paid_at", "final_paid_at",
            "active_payment_path", "cash_payment_mode_snapshot", "delivery_mode",
            "coupon_code", "delivery_address",
            "tracking_number", "estimated_delivery",
            "measurement_profile_id", "notes",
            "escrow_released", "is_test_order",
            "items", "status_history", "payment_records", "commercial_transition_logs",
            "created_at", "updated_at",
        ]


class PlaceOrderItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=False, allow_null=True)
    product_slug = serializers.CharField(required=False, allow_blank=True)
    variant_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)


class PlaceOrderSerializer(serializers.Serializer):
    delivery_address = serializers.DictField(child=serializers.CharField(), required=True)
    fulfillment_type = serializers.ChoiceField(
        choices=["delivery", "pickup", "custom"],
        default="delivery",
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
    measurement_profile_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    items = PlaceOrderItemSerializer(many=True, required=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_delivery_address(self, value):
        if not value.get("address_line_1") or not value.get("city"):
            raise serializers.ValidationError("delivery_address must include address_line_1 and city.")
        return value


class TransitionStatusSerializer(serializers.Serializer):
    new_status = serializers.CharField(required=False)
    status = serializers.CharField(required=False, write_only=True)
    note = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        """Normalize legacy/frontend status aliases to the service contract.

        The backend service accepts ``new_status`` and ``note``. Some FSD
        mutation clients send the more UI-friendly ``status`` and ``notes``.
        Normalizing here keeps API views thin and avoids view-level business
        branching while preserving backward compatibility.
        """
        attrs["new_status"] = attrs.get("new_status") or attrs.get("status")
        attrs["note"] = attrs.get("note") or attrs.get("notes", "")
        if not attrs["new_status"]:
            raise serializers.ValidationError({"new_status": "This field is required."})
        return attrs
