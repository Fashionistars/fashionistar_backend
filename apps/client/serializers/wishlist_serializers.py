from rest_framework import serializers


class WishlistProductSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    pid = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    image = serializers.CharField(read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    old_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    stock_qty = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    category_name = serializers.CharField(source="category.title", read_only=True)


class ClientWishlistSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    product = WishlistProductSerializer(read_only=True)
    date = serializers.DateTimeField(read_only=True)


class WishlistToggleSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)


class WishlistToggleResponseSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["added", "removed"])
