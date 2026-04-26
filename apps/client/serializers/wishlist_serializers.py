from rest_framework import serializers
from store.models import Wishlist, Product

class WishlistProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.title', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'pid', 'title', 'image', 'price', 'old_price', 
            'stock_qty', 'status', 'category_name'
        ]

class ClientWishlistSerializer(serializers.ModelSerializer):
    product = WishlistProductSerializer(read_only=True)
    
    class Meta:
        model = Wishlist
        fields = ['id', 'product', 'date']


class WishlistToggleSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)


class WishlistToggleResponseSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['added', 'removed'])
