from rest_framework import serializers
from .models import Vendor
from store.models import Product

class VendorSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='user.phone')
    address = serializers.CharField(source='user.profile.address')  # Adjust this field according to your Profile model

    class Meta:
        model = Vendor
        fields = ['phone_number', 'address']

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'image', 'description', 'category', 'tags', 'brand', 'price', 'old_price', 'shipping_amount', 'total_price', 'stock_qty', 'in_stock', 'status', 'featured', 'hot_deal', 'special_offer', 'views', 'orders', 'saved', 'slug', 'date']

class VendorStoreSerializer(serializers.Serializer):
    store_name = serializers.CharField()
    phone_number = serializers.CharField()
    address = serializers.CharField()
    products = ProductSerializer(many=True)