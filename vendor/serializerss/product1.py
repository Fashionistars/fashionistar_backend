# vendor/serializers/product1.py

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
class ProductSerializer1(serializers.ModelSerializer):
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