from rest_framework import serializers
from .models import Vendor
from store.models import Product

class AllVendorSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source='user.phone')
    address = serializers.CharField(source='user.profile.address')
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ['name', 'image', 'average_rating', 'phone', 'address', 'slug']

    def get_average_rating(self, obj):
        return obj.get_average_rating()
    
    
class AllProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'image', 'description', 'category', 'tags', 'brand', 'price', 'old_price', 'shipping_amount', 'total_price', 'stock_qty', 'in_stock', 'status', 'featured', 'hot_deal', 'special_offer', 'views', 'orders', 'saved', 'slug', 'date']

class VendorStoreSerializer(serializers.Serializer):
    store_name = serializers.CharField()
    phone_number = serializers.CharField()
    address = serializers.CharField()
    products = AllProductSerializer(many=True)
