from rest_framework import serializers
from store.models import CartOrder, OrderItem, Product

class ClientOrderItemSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='product.title', read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_title', 'product_image', 
            'qty', 'price', 'sub_total', 'shipping_amount', 
            'service_fee', 'total', 'date'
        ]

class ClientCartOrderSerializer(serializers.ModelSerializer):
    orderitem = ClientOrderItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = CartOrder
        fields = [
            'id', 'oid', 'sub_total', 'shipping_amount', 'service_fee', 
            'total', 'payment_status', 'order_status', 'delivery_status', 
            'tracking_id', 'date', 'orderitem'
        ]
