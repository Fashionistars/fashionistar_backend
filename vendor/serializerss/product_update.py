# vendor/Views/product_update.py


from rest_framework import serializers
from admin_backend.models import Category
from store.models import (
    Product, Tag, Gallery, Specification, Size, Color, ProductFaq,
    CartOrder, CartOrderItem, Review, Wishlist, Coupon, CouponUsers, DeliveryCouriers
)
from userauths.serializer import ProfileSerializer, ProtectedUserSerializer
from admin_backend.serializers import CategorySerializer
from django.db import transaction
import logging

application_logger = logging.getLogger('application')

# Gallery Serializer - Now with a create method
class GallerySerializer1(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = ['id', 'image', 'active']

# Specification Serializer - Remains straightforward
class SpecificationSerializer1(serializers.ModelSerializer):
    class Meta:
        model = Specification
        fields = ['id', 'title', 'content']

# Size Serializer - Remains straightforward
class SizeSerializer1(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ['id', 'name', 'price']

# Color Serializer - Remains straightforward
class ColorSerializer1(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ['id', 'name', 'color_code', 'image']

# The Enhanced Product Serializer
class ProductUpdateSerializer1(serializers.ModelSerializer):
    """
    Serializer for the Product model, enhanced for writable nested relationships.
    This serializer can now create a Product along with its related Gallery images,
    Specifications, Sizes, and Colors in a single API call.
    """
    gallery = GallerySerializer1(many=True, required=False)
    specification = SpecificationSerializer1(many=True, required=False)
    size = SizeSerializer1(many=True, required=False)
    color = ColorSerializer1(many=True, required=False)
    # Using PrimaryKeyRelatedField for writable ManyToMany relationship
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True
    )

    class Meta:
        model = Product
        fields = [
            "id", "title", "image", "description", "category", "tags", "brand",
            "price", "old_price", "shipping_amount", "stock_qty", "status",
            "featured", "hot_deal", "special_offer", "slug", "sku", "date",
            "gallery", "specification", "size", "color"
        ]
        read_only_fields = ['slug', 'sku', 'date']

    def create(self, validated_data):
        """
        Overrides the default create method to handle the creation of nested objects.
        This method ensures that all related objects (gallery, specifications, etc.)
        are created and associated with the main product within a single database transaction.
        """
        gallery_data = validated_data.pop('gallery', [])
        specifications_data = validated_data.pop('specification', [])
        sizes_data = validated_data.pop('size', [])
        colors_data = validated_data.pop('color', [])
        categories = validated_data.pop('category')

        # Create the Product instance
        product = Product.objects.create(**validated_data)

        # Set the categories
        product.category.set(categories)

        # Create nested objects
        for gallery_item_data in gallery_data:
            Gallery.objects.create(product=product, **gallery_item_data)

        for spec_data in specifications_data:
            Specification.objects.create(product=product, **spec_data)

        for size_data in sizes_data:
            Size.objects.create(product=product, **size_data)

        for color_data in colors_data:
            Color.objects.create(product=product, **color_data)

        application_logger.info(f"Product '{product.title}' and its related objects created successfully.")
        return product

    def to_representation(self, instance):
        """
        Customize the output representation to include full category details.
        """
        representation = super().to_representation(instance)
        representation['category'] = CategorySerializer(instance.category.all(), many=True).data
        return representation




    # ... (inside the ProductSerializer class)

    def update(self, instance, validated_data):
        """
        Overrides the default update method to handle writable nested relationships.

        This method ensures that when a product is updated, its related nested
        objects (gallery, specifications, etc.) are replaced with the new data
        provided in the request. The entire operation is atomic.
        """
        # Pop nested data to handle them separately. `None` is a valid default if
        # a key is not present in a PATCH request.
        gallery_data = validated_data.pop('gallery', None)
        specifications_data = validated_data.pop('specification', None)
        sizes_data = validated_data.pop('size', None)
        colors_data = validated_data.pop('color', None)
        categories = validated_data.pop('category', None)

        # --- Update the core Product instance ---
        # This loop updates the simple fields on the Product model itself.
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # --- Update Many-to-Many and Reverse Foreign Key relationships ---

        # Handle ManyToMany categories update
        if categories is not None:
            instance.category.set(categories)

        # This "delete and recreate" pattern is robust for handling updates from a form
        # where the user submits the complete desired state of the product.
        if gallery_data is not None:
            instance.gallery.all().delete() # Delete old gallery images
            for gallery_item_data in gallery_data:
                Gallery.objects.create(product=instance, **gallery_item_data)

        if specifications_data is not None:
            instance.specification.all().delete() # Delete old specifications
            for spec_data in specifications_data:
                Specification.objects.create(product=instance, **spec_data)

        if sizes_data is not None:
            instance.size.all().delete() # Delete old sizes
            for size_data in sizes_data:
                Size.objects.create(product=instance, **size_data)

        if colors_data is not None:
            instance.color.all().delete() # Delete old colors
            for color_data in colors_data:
                Color.objects.create(product=instance, **color_data)

        application_logger.info(f"Product '{instance.title}' and its related objects updated successfully.")
        return instance







# +++  OR THIS +++++++++++








from rest_framework import serializers
from django.db import transaction
import json
import uuid




class ProductUpdateSerializer(serializers.ModelSerializer):
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




    # ... (inside the ProductSerializer class)

    def update(self, instance, validated_data):
        """
        Overrides the default update method to handle writable nested relationships.

        This method ensures that when a product is updated, its related nested
        objects (gallery, specifications, etc.) are replaced with the new data
        provided in the request. The entire operation is atomic.
        """
        # Pop nested data to handle them separately. `None` is a valid default if
        # a key is not present in a PATCH request.
        gallery_data = validated_data.pop('gallery', None)
        specifications_data = validated_data.pop('specification', None)
        sizes_data = validated_data.pop('size', None)
        colors_data = validated_data.pop('color', None)
        categories = validated_data.pop('category', None)

        # --- Update the core Product instance ---
        # This loop updates the simple fields on the Product model itself.
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # --- Update Many-to-Many and Reverse Foreign Key relationships ---

        # Handle ManyToMany categories update
        if categories is not None:
            instance.category.set(categories)

        # This "delete and recreate" pattern is robust for handling updates from a form
        # where the user submits the complete desired state of the product.
        if gallery_data is not None:
            instance.gallery.all().delete() # Delete old gallery images
            for gallery_item_data in gallery_data:
                Gallery.objects.create(product=instance, **gallery_item_data)

        if specifications_data is not None:
            instance.specification.all().delete() # Delete old specifications
            for spec_data in specifications_data:
                Specification.objects.create(product=instance, **spec_data)

        if sizes_data is not None:
            instance.size.all().delete() # Delete old sizes
            for size_data in sizes_data:
                Size.objects.create(product=instance, **size_data)

        if colors_data is not None:
            instance.color.all().delete() # Delete old colors
            for color_data in colors_data:
                Color.objects.create(product=instance, **color_data)

        application_logger.info(f"Product '{instance.title}' and its related objects updated successfully.")
        return instance




