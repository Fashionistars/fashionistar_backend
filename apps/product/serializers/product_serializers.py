# apps/product/serializers/product_serializers.py
"""
Serializers for the Product domain.

Separate serializers for:
  - Public listing (minimal, fast)
  - Public detail (full data)
  - Vendor write (create/update)
  - Admin (full + status management)
"""

from rest_framework import serializers

from apps.product.models import (
    Product,
    ProductGalleryMedia,
    ProductSize,
    ProductColor,
    ProductTag,
    ProductSpecification,
    ProductFaq,
    ProductVariant,
    ProductReview,
    ProductWishlist,
    Coupon,
    DeliveryCourier,
)


# ─── Gallery ──────────────────────────────────────────────────────────────────

class ProductGalleryMediaSerializer(serializers.ModelSerializer):
    media_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductGalleryMedia
        fields = ["id", "media_url", "media_type", "alt_text", "ordering"]

    def get_media_url(self, obj):
        if obj.media:
            return str(obj.media.url)
        return None


# ─── Size / Color / Tag ───────────────────────────────────────────────────────

class ProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSize
        fields = ["id", "name"]


class ProductColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductColor
        fields = ["id", "name", "hex_code"]


class ProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = ["id", "name", "slug"]


# ─── Specification / FAQ ──────────────────────────────────────────────────────

class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ["id", "title", "content"]


class ProductFaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFaq
        fields = ["id", "question", "answer"]


# ─── Variant ──────────────────────────────────────────────────────────────────

class ProductVariantSerializer(serializers.ModelSerializer):
    size = ProductSizeSerializer(read_only=True)
    color = ProductColorSerializer(read_only=True)
    size_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductSize.objects.all(), source="size", write_only=True, required=False
    )
    color_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductColor.objects.all(), source="color", write_only=True, required=False
    )
    effective_price = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = [
            "id", "sku", "size", "size_id", "color", "color_id",
            "price_override", "effective_price", "stock_qty", "is_active",
        ]


# ─── Product List (public, fast) ──────────────────────────────────────────────

class ProductListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    discount_percentage = serializers.ReadOnlyField()
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    vendor_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "sku", "price", "old_price",
            "discount_percentage", "currency", "image_url",
            "in_stock", "stock_qty", "featured", "hot_deal",
            "rating", "review_count", "status",
            "category_name", "brand_name", "vendor_name",
            "requires_measurement", "is_customisable",
            "created_at",
        ]

    def get_image_url(self, obj):
        if obj.image:
            return str(obj.image.url)
        return None

    def get_vendor_name(self, obj):
        if obj.vendor:
            return getattr(obj.vendor, "business_name", None) or str(obj.vendor)
        return None


# ─── Product Detail (public, full) ────────────────────────────────────────────

class ProductDetailSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    discount_percentage = serializers.ReadOnlyField()
    gallery = ProductGalleryMediaSerializer(many=True, read_only=True)
    sizes = ProductSizeSerializer(many=True, read_only=True)
    colors = ProductColorSerializer(many=True, read_only=True)
    tags = ProductTagSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(many=True, read_only=True)
    faqs = ProductFaqSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    vendor_name = serializers.SerializerMethodField()
    vendor_id = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "sku", "description", "short_description",
            "price", "old_price", "discount_percentage", "currency",
            "shipping_amount", "image_url", "gallery",
            "in_stock", "stock_qty", "views", "orders_count",
            "rating", "review_count", "featured", "hot_deal", "digital",
            "requires_measurement", "is_customisable",
            "sizes", "colors", "tags",
            "specifications", "faqs", "variants",
            "status", "category_name", "brand_name",
            "vendor_name", "vendor_id",
            "commission_rate",
            "created_at", "updated_at",
        ]

    def get_image_url(self, obj):
        if obj.image:
            return str(obj.image.url)
        return None

    def get_vendor_name(self, obj):
        if obj.vendor:
            return getattr(obj.vendor, "business_name", None) or str(obj.vendor)
        return None

    def get_vendor_id(self, obj):
        return str(obj.vendor.id) if obj.vendor else None


# ─── Vendor Write ─────────────────────────────────────────────────────────────

class ProductWriteSerializer(serializers.ModelSerializer):
    size_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductSize.objects.all(), many=True,
        source="sizes", required=False,
    )
    color_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductColor.objects.all(), many=True,
        source="colors", required=False,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductTag.objects.all(), many=True,
        source="tags", required=False,
    )

    class Meta:
        model = Product
        fields = [
            "title", "description", "short_description",
            "price", "old_price", "currency", "shipping_amount",
            "stock_qty", "category", "sub_category", "brand",
            "size_ids", "color_ids", "tag_ids",
            "requires_measurement", "is_customisable",
            "hot_deal", "digital", "commission_rate",
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_stock_qty(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative.")
        return value

    def create(self, validated_data):
        sizes = validated_data.pop("sizes", [])
        colors = validated_data.pop("colors", [])
        tags = validated_data.pop("tags", [])
        product = Product.objects.create(**validated_data)
        product.sizes.set(sizes)
        product.colors.set(colors)
        product.tags.set(tags)
        return product

    def update(self, instance, validated_data):
        sizes = validated_data.pop("sizes", None)
        colors = validated_data.pop("colors", None)
        tags = validated_data.pop("tags", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if sizes is not None:
            instance.sizes.set(sizes)
        if colors is not None:
            instance.colors.set(colors)
        if tags is not None:
            instance.tags.set(tags)
        return instance
