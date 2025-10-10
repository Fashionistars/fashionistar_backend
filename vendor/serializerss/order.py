# vendor/serializerss/order.py

from rest_framework import serializers



from store.models import CartOrder, CartOrderItem


class VendorOrderItemSerializer(serializers.ModelSerializer):
    """
    A simplified serializer for displaying order items within an order detail view.
    It provides essential product information for the vendor.
    """
    product_title = serializers.CharField(source='product.title', read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)

    class Meta:
        model = CartOrderItem
        fields = [
            'product_title',
            'product_image',
            'qty',
            'price',
            'total',
        ]

class VendorOrderListSerializer(serializers.ModelSerializer):
    """
    A tailored serializer for the Vendor's main "Orders" list page.

    Provides a concise, summary view of each order as depicted in the Figma design,
    including an optimized count of the items within the order.
    """
    # Using SerializerMethodField to efficiently get the customer's name.
    customer_name = serializers.CharField(source='buyer.profile.full_name', read_only=True)
    # Using SerializerMethodField to get the total number of items in the order.
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = CartOrder
        fields = [
            'oid',
            'date',
            'customer_name',
            'address', # Assuming the main address is stored here
            'payment_status',
            'order_status',
            'items_count',
        ]

    def get_items_count(self, obj):
        """Calculates the total number of items in the order."""
        # This uses the reverse relationship manager, which is efficient.
        return obj.cart_order.count()

class VendorOrderDetailSerializer(serializers.ModelSerializer):
    """
    A comprehensive serializer for the "Order Details" page.

    Provides detailed information about the customer, the order, delivery, and includes
    a nested list of all items in the order.
    """
    # Nested serializer to display all items within the order.
    # The source 'cart_order' matches the related_name on the CartOrderItem's ForeignKey.
    items = VendorOrderItemSerializer(source='cart_order', many=True, read_only=True)
    customer_name = serializers.CharField(source='buyer.profile.full_name', read_only=True)
    customer_email = serializers.CharField(source='buyer.email', read_only=True)
    customer_phone = serializers.CharField(source='buyer.profile.phone', read_only=True)

    class Meta:
        model = CartOrder
        fields = [
            'oid',
            'date',
            'order_status',
            'payment_status',
            'customer_name',
            'customer_email',
            'customer_phone',
            'shipping_amount',
            'sub_total',
            'total',
            'address',
            'city',
            'state',
            'country',
            'items',
        ]

class OrderActionSerializer(serializers.Serializer):
    """
    A dedicated serializer for validating vendor actions on an order.
    Ensures that only permitted actions ('accept', 'reject') are processed.
    """
    action = serializers.ChoiceField(choices=['accept', 'reject'])