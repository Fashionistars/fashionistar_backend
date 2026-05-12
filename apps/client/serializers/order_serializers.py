from rest_framework import serializers


class ClientOrderItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    product = serializers.CharField(read_only=True)
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_image = serializers.CharField(source="product.image", read_only=True)
    qty = serializers.IntegerField(read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    sub_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    service_fee = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    date = serializers.DateTimeField(read_only=True)


class ClientCartOrderSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    oid = serializers.CharField(read_only=True)
    sub_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    service_fee = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    order_status = serializers.CharField(read_only=True)
    delivery_status = serializers.CharField(read_only=True)
    tracking_id = serializers.CharField(read_only=True)
    date = serializers.DateTimeField(read_only=True)
    orderitem = ClientOrderItemSerializer(many=True, read_only=True)
