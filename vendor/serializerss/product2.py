# vendor/serializerss/product2.py

from rest_framework import serializers
from django.db import transaction
import json
import uuid

from store.models import Product, Gallery, Specification, Size, Color
from admin_backend.models import Category
from vendor.models import Vendor

# ====================================================================
# SERIALIZERS FOR LISTING / RETRIEVING PRODUCTS (READ-ONLY)
# ====================================================================

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        # Added 'id' so the frontend knows which UUID to use
        fields = ['id', 'name', 'slug']

class GallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = ['image', 'active']

class SpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specification
        fields = ['title', 'content']

class SizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ['name', 'price']

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ['name', 'color_code', 'image']

class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['name', 'image', 'vid']

class ProductListDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for LISTING and RETRIEVING products.
    Provides a rich, nested representation of a product and its related data.
    """
    vendor = VendorSerializer(read_only=True)
    category = CategorySerializer(many=True, read_only=True)
    gallery = GallerySerializer(many=True, read_only=True)
    specification = SpecificationSerializer(many=True, read_only=True)
    size = SizeSerializer(many=True, read_only=True)
    color = ColorSerializer(many=True, read_only=True)

    product_rating = serializers.ReadOnlyField()
    rating_count = serializers.ReadOnlyField()
    get_precentage = serializers.ReadOnlyField()
    
    # Adding model methods/properties to the output
    discount_percentage = serializers.FloatField(source='get_precentage', read_only=True)
    average_rating = serializers.FloatField(source='product_rating', read_only=True)

    class Meta:
        model = Product
        fields = [
            'pid', 'sku', 'title', 'image', 'description', 'price', 'old_price',
            'shipping_amount', 'total_price', 'stock_qty', 'in_stock', 'status',
            'featured', 'hot_deal', 'slug', 'date',
            'vendor', 'category', 'gallery', 'specification', 'size', 'color'
            'product_rating', 'rating_count', 'get_precentage',  'discount_percentage', 'average_rating',
            'brand', 'tags','order_count', 'views', 'saved',
        ]

# ====================================================================
# SERIALIZER FOR CREATING A PRODUCT (WRITE-ONLY)
# ====================================================================

class ProductCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for CREATING a new product.
    Handles multipart/form-data including the main image, gallery images,
    and JSON-encoded strings for nested objects (specifications, sizes, colors).
    """
    image = serializers.ImageField(required=True, write_only=True)
    
    # --- THIS IS THE FIX ---
    # We now accept a JSON string of UUIDs instead of a direct list.
    category = serializers.CharField(
        write_only=True,
        required=True,
        help_text='A JSON-encoded list of Category UUIDs. Example: \'["a1b2c3d4...", "e5f6g7h8..."]\''
    )
    
    # Writable fields for nested objects (sent as JSON strings)
    specifications = serializers.CharField(write_only=True, required=False, help_text='A JSON-encoded list of specification objects.')
    sizes = serializers.CharField(write_only=True, required=False, help_text='A JSON-encoded list of size objects.')
    colors = serializers.CharField(write_only=True, required=False, help_text='A JSON-encoded list of color objects.')

    # Writable field for multiple gallery images
    gallery_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False
    )
    

    class Meta:
        model = Product
        fields = [
            'title', 'image', 'description', 'category', 'price', 'old_price',
            'shipping_amount', 'stock_qty', 'brand', 'tags', 'status', 'featured',
            # Write-only fields
            'specifications', 'sizes', 'colors', 'gallery_images',
        ]

    def _validate_json_string(self, value, field_name):
        """Helper function to validate and decode a JSON string."""
        try:
            decoded_list = json.loads(value)
            if not isinstance(decoded_list, list):
                raise serializers.ValidationError({field_name: "This field must be a JSON-encoded list."})
            return decoded_list
        except json.JSONDecodeError:
            raise serializers.ValidationError({field_name: f"Invalid JSON format for {field_name}."})

    def validate_category(self, value):
        """Validate the JSON string for categories and convert to Category objects."""
        category_uuids = self._validate_json_string(value, 'category')
        
        # Check if all items in the list are valid UUIDs
        valid_uuids = []
        for item in category_uuids:
            try:
                valid_uuids.append(uuid.UUID(item))
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Invalid UUID format in category list: '{item}'")
        
        # Check if all UUIDs correspond to existing categories
        categories = Category.objects.filter(id__in=valid_uuids)
        if len(categories) != len(valid_uuids):
            raise serializers.ValidationError("One or more category UUIDs are invalid or do not exist.")
            
        return categories

    def validate(self, attrs):
        """Validate other JSON string fields."""
        for field_name in ['specifications', 'sizes', 'colors']:
            if field_name in attrs:
                attrs[field_name] = self._validate_json_string(attrs[field_name], field_name)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Handle the creation of a product and its nested relationships
        within a single database transaction.
        """
        # Pop nested data before creating the product
        categories_data = validated_data.pop('category')
        specifications_data = validated_data.pop('specifications', [])
        sizes_data = validated_data.pop('sizes', [])
        colors_data = validated_data.pop('colors', [])
        
        gallery_images = self.context.get('gallery_images', [])

        with transaction.atomic():
            # Create the product instance
            product = Product.objects.create(**validated_data)
        
            # Set the ManyToMany relationship for categories
            product.category.set(categories_data)
            
            # Create nested objects
            for spec in specifications_data:
                Specification.objects.create(product=product, **spec)
                
            for size in sizes_data:
                Size.objects.create(product=product, **size)
                
            for color in colors_data:
                Color.objects.create(product=product, **color)
                
            for image in gallery_images:
                Gallery.objects.create(product=product, image=image)

        return product