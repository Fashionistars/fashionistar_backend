from rest_framework import serializers
from store.models import Product
from vendor.models import Vendor

from userauths.models import User  # Import User model (if needed in the serializer)


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







# class VendorSerializer(serializers.ModelSerializer):
#     # We can include a field for the user that will be assigned automatically
#     user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)  # This will attach the user via the ID
    
#     class Meta:
#         model = Vendor
#         fields = ['user', 'image', 'name', 'email', 'description', 'mobile', 'verified', 'active', 'wallet_balance', 'transaction_password']
#         read_only_fields = ['wallet_balance', 'date', 'vid', 'slug']  # These fields will be handled by default
        
#     def validate(self, data):
#         """
#         Custom validation can be added here.
#         For example, ensuring the email is unique, checking if image is provided, etc.
#         """
#         if 'email' in data and Vendor.objects.filter(email=data['email']).exists():
#             raise serializers.ValidationError("A vendor with this email already exists.")
        
#         # Additional validation can go here if needed

#         return data

#     def create(self, validated_data):
#         """
#         This is where the vendor object will be created.
#         We can add any additional custom logic during object creation here.
#         """
#         # Ensure that 'user' is provided from the request (This can be set in the `VendorRegister` view)
#         user = validated_data.get('user')
#         if not user:
#             raise serializers.ValidationError("User must be provided.")
        
#         # Create the vendor
#         vendor = Vendor.objects.create(**validated_data)
        
#         # Optionally, you can set additional fields that are not provided in the input here
#         # For example, setting a default wallet balance or generating a slug if not provided
        
#         return vendor






class VendorSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)  # Optionally, you can make this required as well
    
    class Meta:
        model = Vendor
        fields = ['user', 'image', 'name', 'email', 'description', 'mobile', 'verified', 'active', 'wallet_balance', 'transaction_password']
        read_only_fields = ['wallet_balance', 'date', 'vid', 'slug']  # Fields to be auto-filled or not edited

    def validate(self, data):
        """
        Custom validation can be added here.
        For example, ensuring the email is unique, checking if the user is authenticated, etc.
        """
        if 'email' in data and Vendor.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError("A vendor with this email already exists.")
        
        # Ensure the user is attached (this can be optional depending on your use case)
        if not data.get('user'):
            raise serializers.ValidationError("User must be associated with the vendor.")
        
        return data

    def create(self, validated_data):
        """
        Ensure that the user is set properly during creation.
        """
        user = validated_data.get('user')
        
        if not user:
            raise serializers.ValidationError("User must be provided.")

        # Create and return the vendor object
        vendor = Vendor.objects.create(**validated_data)
        
        return vendor
