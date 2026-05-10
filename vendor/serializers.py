from rest_framework import serializers
from store.models import Product
from vendor.models import Vendor

from userauths.models import User  # Import User model (if needed in the serializer)


class AllVendorSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source='user.phone', help_text="Vendor's phone number")
    address = serializers.CharField(source='user.profile.address', help_text="Vendor's address")
    average_rating = serializers.SerializerMethodField(help_text="Average rating of the vendor")
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
    store_name = serializers.CharField(help_text="Name of the vendor's store")
    phone_number = serializers.CharField(help_text="Vendor's phone number")
    address = serializers.CharField(help_text="Address of the vendor's store")
    products = AllProductSerializer(many=True, help_text="Products available in the vendor's store")


class AllVENDORSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor  # <-- Change this from User to Vendor
        fields = '__all__'







from rest_framework import serializers
from userauths.models import User
from vendor.models import Vendor
from vendor.utils import fetch_user_and_vendor
from rest_framework.exceptions import ValidationError
from django.db.models import Avg


class VendorSerializer(serializers.ModelSerializer):
    """
    Serializer for the Vendor model.

    This serializer handles the creation, validation, and updating of vendor
    instances. It includes fields for user association, shop details, contact
    information, verification status, activity status, wallet balance, and
    transaction password.

    Fields:
        user: A PrimaryKeyRelatedField for the associated User.
        image: An ImageField for the vendor's shop image.
        name: A CharField for the vendor's shop name.
        email: An EmailField for the vendor's shop email.
        description: A TextField for the vendor's shop description.
        mobile: A CharField for the vendor's mobile number.
        verified: A BooleanField indicating if the vendor is verified.
        active: A BooleanField indicating if the vendor is active.
        wallet_balance: A DecimalField for the vendor's wallet balance (read-only).
        transaction_password: A CharField for the vendor's transaction password.
        average_rating: A SerializerMethodField to get the average rating of the vendor's products

    Meta:
        model: The Vendor model to be serialized.
        fields: List of fields to be included in the serialization.
        read_only_fields: List of fields that are read-only.

    Methods:
        validate(data): Custom validation logic.
        create(validated_data): Custom creation logic.

    """
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=True)  # User field is required
    average_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Vendor
        fields = ['user', 'image', 'name', 'email', 'description', 'mobile', 'verified', 'active', 'wallet_balance', 'transaction_password', 'average_rating']
        read_only_fields = ['wallet_balance', 'date', 'vid', 'slug']  # These fields will be handled by default
        
    def get_average_rating(self, obj):
        """
        Get the average rating for all products associated with the vendor

        Args:
          obj (Vendor): The Vendor instance.

        Returns:
            float: The average rating for the vendor.
        """
        return obj.vendor_role.aggregate(average_rating=Avg('rating')).get('average_rating', 0)
    

    def validate(self, data):
        """
        Custom validation for VendorSerializer.

        Validates that the email is unique, name is unique, user is attached, and if the user is not already associated with another vendor.
         
        Args:
          data (dict): The input data from the request.
          
        Raises:
            ValidationError: If the email, name is not unique, or the user is not attached, or is already associated with another vendor.

        Returns:
            dict: The validated data.
        """
        
        user = data.get('user')
        name = data.get('name')
        email = data.get('email')
        
        if not user:
          raise serializers.ValidationError("User must be associated with the vendor.")
        
        # Check if the user already has a vendor profile
        if hasattr(user, 'vendor_profile'):
            raise serializers.ValidationError("A VENDOR profile already exists for this user.")

        if email and Vendor.objects.filter(email=email).exists():
             raise serializers.ValidationError("A vendor with this email already exists.")

        if name and Vendor.objects.filter(name=name).exists():
            raise serializers.ValidationError("A vendor with this name already exists.")
        
        return data

    def create(self, validated_data):
        """
        Create a new Vendor instance.

        Ensures that the user is set properly during creation and any other additional fields needed to create the vendor.

        Args:
            validated_data (dict): Validated data for creating the vendor

         Returns:
           Vendor: The newly created Vendor object

         Raises:
              ValidationError: If the User is not attached.
        """
        
        user = validated_data.get('user')
        
        if not user:
            raise serializers.ValidationError("User must be provided.")

        # Create and return the vendor object
        vendor = Vendor.objects.create(**validated_data)
        
        return vendor


















