# apps/product/serializers/product_serializers.py
"""
Enterprise DRF Serializers for the Product domain.

Serializer hierarchy:
  ProductVendorMiniSerializer   — tiny vendor card embedded in product
  ProductGalleryMediaSerializer — gallery item read
  ProductSizeAndMeasurementGuideSerializer         — flat taxonomy
  ProductColorSerializer        — flat taxonomy with hex
  ProductTagSerializer          — flat taxonomy with slug
  ProductSpecificationSerializer
  ProductFaqSerializer
  ProductVariantSerializer      — per-SKU variant (read + write)
  ProductListSerializer         — public catalog card (fast, .only() safe)
  ProductDetailSerializer       — public PDP (full + reverse relations)
  ProductWriteSerializer        — vendor create/update (validates all fields)
  ProductAdminSerializer        — moderator full access (status mutation)
  ProductInventoryLogSerializer — stock history list
  ProductWishlistSerializer     — wishlist entry with embedded product

Rules:
  - Read serializers NEVER hit extra DB queries (use SerializerMethodField
    only when source data is already select_related / prefetched).
  - Write serializers delegate persistence to the service layer — never
    call Product.objects.create() directly; the view must pass through
    the service so audit + idempotency guards run.
  - image_url / media_url always return absolute Cloudinary secure_url.
  - All UUIDs serialized as str, not int.
"""

from __future__ import annotations

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Category
from apps.product.models import (
    Coupon,
    Product,
    ProductFabric,
    ProductSizeAndMeasurementGuide,
    ProductSpecification,
    ProductFaq,
    ProductVariantGalleryMedia,
    ProductTag,
    ProductReview,
    ProductInventoryLog,
    ProductWishlist,
    ProductDraftSession,
    ProductShippingProfile,
)


# ─────────────────────────────────────────────────────────────────────────────
# ATOMIC TAXONOMY SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────


class ProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = ["id", "name", "slug"]


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 NEW TAXONOMY SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductFabricSerializer(serializers.ModelSerializer):
    """Fabric type with care/sustainability meta — Phase 1."""
    class Meta:
        model = ProductFabric
        fields = [
            "id",
            "fabric_type",
            "composition",
            "care_instructions",
            "care_notes",
            "is_organic",
            "is_vegan",
            "country_of_origin",
        ]

class ProductSizeAndMeasurementGuideSerializer(serializers.ModelSerializer):
    """Flat sizing serializer mapping ProductSizeAndMeasurementGuide to output."""
     
    SIZE_CHOICES = [
        ("XS", _("XS")),
        ("S", _("S")),
        ("M", _("M")),
        ("L", _("L")),
        ("XL", _("XL")),
        ("XXL", _("XXL")),
        ("Custom", _("Custom")),
    ]
    
    DESCRIPTION_CHOICES = [
        ("clothing", _("Clothing")),
        ("footwear", _("Footwear")),
        ("accessory", _("Accessory")),
        ("measurement", _("Measurement-Based")),
        ("custom", _("Custom")),
    ]

    id = serializers.UUIDField(source="id", read_only=True)
    name = serializers.CharField(source="name")
    description = serializers.ChoiceField(source="description", choices=DESCRIPTION_CHOICES)
    size_label = serializers.ChoiceField(source="size_label", choices=SIZE_CHOICES)

    class Meta:
        model = ProductSizeAndMeasurementGuide
        fields = [
            "id",
            "vendor",
            "name",
            "description", 
            "size_label", 
            "chest_cm",
            "waist_cm",
            "hip_cm",
            "shoulder_cm",
            "sleeve_cm",
            "length_cm",
            "inseam_cm",
            "foot_length_cm",
            "sort_order",
            "save_as_template",
        ]


ProductMeasurementGuideSerializer = ProductSizeAndMeasurementGuideSerializer


class ProductShippingProfileSerializer(serializers.ModelSerializer):
    """Per-product shipping configuration — Phase 1."""
    class Meta:
        model = ProductShippingProfile
        fields = [
            "id",
            "weight_kg",
            "length_cm",
            "width_cm",
            "height_cm",
            "is_fragile",
            "requires_signature",
            "restricted_countries",
            "free_shipping_threshold",
            "processing_days",
        ]






# ─────────────────────────────────────────────────────────────────────────────
# VENDOR MINI EMBED
# ─────────────────────────────────────────────────────────────────────────────

class ProductVendorMiniSerializer(serializers.Serializer):
    """
    Thin vendor embed that avoids hitting the vendor FK multiple times.
    Only uses data that is select_related(vendor__user) — zero extra queries.
    """
    id = serializers.UUIDField(source="vendor.id")
    store_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()

    def get_store_name(self, obj):
        vendor = obj.vendor
        if not vendor:
            return None
        return (
            getattr(vendor, "store_name", None)
            or getattr(vendor, "business_name", None)
            or str(vendor)
        )

    def get_avatar_url(self, obj):
        vendor = obj.vendor
        if not vendor:
            return None
        logo = getattr(vendor, "logo", None) or getattr(vendor, "avatar", None)
        return str(logo.url) if logo else None

    def get_slug(self, obj):
        vendor = obj.vendor
        return getattr(vendor, "slug", None) if vendor else None

    def get_is_verified(self, obj):
        vendor = obj.vendor
        return getattr(vendor, "is_verified", False) if vendor else False


# ─────────────────────────────────────────────────────────────────────────────
# SPECIFICATION / FAQ
# ─────────────────────────────────────────────────────────────────────────────

class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ["id", "title", "content"]


class ProductFaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFaq
        fields = ["id", "question", "answer"]


# ─────────────────────────────────────────────────────────────────────────────
# VARIANT GALLERY MEDIA
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantGalleryMediaSerializer(serializers.ModelSerializer):
    """Consolidated variant, color, and media serializer."""
    effective_price = serializers.ReadOnlyField()
    image_url = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    video_thumbnail_url = serializers.SerializerMethodField()
    swatch_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariantGalleryMedia
        fields = [
            "id", "sku",
            "size", "size_id",
            "color_name", "color_hex", "swatch_image_url",
            "price_override", "effective_price",
            "stock_qty", "is_active", "is_default",
            "barcode", "weight_kg", "dimensions_cm", "notes",
            "image_url", "media_url", "thumbnail_url",
            "media_type", "alt_text", "ordering", "is_primary",
            "video_thumbnail_url", "duration_sec",
        ]

    def get_image_url(self, obj):
        return str(obj.image.url) if obj.image else None

    def get_media_url(self, obj):
        return str(obj.media.url) if obj.media else None

    def get_thumbnail_url(self, obj):
        if not obj.media or obj.media_type != "image":
            return None
        url = str(obj.media.url)
        if "res.cloudinary.com" in url:
            return url.replace("/upload/", "/upload/w_400,h_400,c_fill,f_auto,q_auto/")
        return url

    def get_video_thumbnail_url(self, obj):
        vt = getattr(obj, "video_thumbnail", None)
        return str(vt.url) if vt else None

    def get_swatch_image_url(self, obj):
        if not getattr(obj, "swatch_image", None):
            return None
        url = str(obj.swatch_image.url)
        if "res.cloudinary.com" in url:
            return url.replace("/upload/", "/upload/w_64,h_64,c_fill,f_auto,q_auto/")
        return url


class ProductVariantGalleryMediaWriteSerializer(serializers.ModelSerializer):
    """
    Write-only nested variant/gallery item for ProductWriteFullSerializer.
    """
    size_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductSizeAndMeasurementGuide.objects.all(),
        source="size",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ProductVariantGalleryMedia
        fields = [
            "sku",
            "size_id",
            "color_name", "color_hex",
            "price_override",
            "stock_qty",
            "is_active",
            "is_default",
            "barcode",
            "weight_kg",
            "dimensions_cm",
            "notes",
            "media",
            "image",
            "media_type",
            "alt_text",
            "ordering",
            "is_primary",
            "video_thumbnail",
            "duration_sec",
        ]

    def validate_sku(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("SKU cannot be blank.")
        return value.strip().upper()

    def validate_stock_qty(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative.")
        return value

    def validate_price_override(self, value):
        if value is not None and value < 5000:
            raise serializers.ValidationError("Price override must be at least ₦5,000.00.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT LIST  (catalog / search — card view, fast)
# ─────────────────────────────────────────────────────────────────────────────

class ProductListSerializer(serializers.ModelSerializer):
    """
    Fast read-only serializer for list/search endpoints.
    Paired with get_published_products_list() selector that uses .only()
    so no large text columns are loaded.

    All computed fields use data already prefetched by the selector —
    zero extra queries per row.
    """
    image_url = serializers.SerializerMethodField()
    discount_percentage = serializers.ReadOnlyField()
    category_name = serializers.SerializerMethodField()
    category_slug = serializers.SerializerMethodField()
    brand_name = serializers.SerializerMethodField()
    brand_slug = serializers.SerializerMethodField()
    vendor_name = serializers.SerializerMethodField()
    vendor_slug = serializers.SerializerMethodField()
    # Annotation from selector (Count("reviews"))
    computed_review_count = serializers.IntegerField(read_only=True, default=0)
    computed_avg_rating = serializers.FloatField(read_only=True, default=0)
    # Sizes/colors for filter chips on cards
    sizes = ProductSizeAndMeasurementGuideSerializer(many=True, read_only=True)
    colors = serializers.SerializerMethodField()

    def get_colors(self, obj):
        return obj.color()

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "sku",
            "price", "old_price", "discount_percentage", "currency",
            "image_url",
            "in_stock", "stock_qty",
            "featured", "hot_deal", "digital",
            "rating", "review_count",
            "computed_review_count", "computed_avg_rating",
            "category_name", "category_slug",
            "brand_name", "brand_slug",
            "vendor_name", "vendor_slug",
            "requires_measurement", "is_customisable",
            "sizes", "colors",
            "created_at",
        ]

    def get_image_url(self, obj):
        if obj.image:
            url = str(obj.image.url)
            # Auto-inject Cloudinary transforms for card thumbnails
            if "res.cloudinary.com" in url and "/upload/" in url:
                return url.replace(
                    "/upload/",
                    "/upload/w_480,h_480,c_fill,f_auto,q_auto/",
                )
            return url
        return None

    def get_vendor_name(self, obj):
        if not obj.vendor:
            return None
        return (
            getattr(obj.vendor, "store_name", None)
            or getattr(obj.vendor, "business_name", None)
            or str(obj.vendor)
        )

    def get_vendor_slug(self, obj):
        return getattr(obj.vendor, "store_slug", None) if obj.vendor else None

    def get_category_name(self, obj):
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "name", None)

    def get_category_slug(self, obj):
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "slug", None)

    def get_brand_name(self, obj):
        """Return no product brand because Brand is now company marketing metadata."""
        return None

    def get_brand_slug(self, obj):
        """Return no product brand because Brand is now company marketing metadata."""
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT DETAIL  (public PDP — full)
# ─────────────────────────────────────────────────────────────────────────────

class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full product data for the product detail page.
    Paired with get_product_detail() which selects ALL related objects
    in a single queryset using prefetch/select chains.  Zero extra queries.


    Phase 1 expansions:
      - fabric       → ProductFabricSerializer (one-to-many via reverse FK)
      - measurement_guide → ProductMeasurementGuideSerializer (size chart rows)
        c   
      - Phase 1 Product fields: weight_kg, condition, is_pre_order, pre_order_date,
        meta_title, meta_description, age_group, gender_target
    """
    image_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()  # alias for FE consistency
    gallery = serializers.SerializerMethodField()

    def get_gallery(self, obj):
        return ProductVariantGalleryMediaSerializer(
            obj.gallery(),
            many=True,
        ).data
    sizes = ProductSizeAndMeasurementGuideSerializer(many=True, read_only=True)
    colors = serializers.SerializerMethodField()
    tags = ProductTagSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(
        many=True,
        read_only=True,
        source="product_specifications",
    )
    faqs = ProductFaqSerializer(many=True, read_only=True, source="product_faqs")
    variants = ProductVariantGalleryMediaSerializer(
        many=True,
        read_only=True,
        source="variants",
    )

    def get_colors(self, obj):
        return obj.color()
    # Phase 1 reverse FK embeds
    fabric = ProductFabricSerializer(read_only=True, source="product_fabric")
    measurement_guide = ProductMeasurementGuideSerializer(
        many=True,
        read_only=True,
        source="product_measurement_guide",
    )
    shipping_profile = ProductShippingProfileSerializer(
        read_only=True,
        source="product_custom_shipping_profile",
    )
    # certifications = ProductCertificationSerializer(many=True, read_only=True, source="product_certifications")
    category_name = serializers.SerializerMethodField()
    category_slug = serializers.SerializerMethodField()
    sub_category_name = serializers.SerializerMethodField()
    brand_name = serializers.SerializerMethodField()
    brand_slug = serializers.SerializerMethodField()
    vendor = ProductVendorMiniSerializer(source="*", read_only=True)
    computed_review_count = serializers.IntegerField(read_only=True, default=0)
    computed_avg_rating = serializers.FloatField(read_only=True, default=0)

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "sku",
            "description",
            "price", "old_price", "discount_percentage", "currency",
            "shipping_amount",
            "image_url", "cover_image_url", "gallery",
            "in_stock", "stock_qty", "max_stock",
            "views", "orders_count",
            "rating", "review_count",
            "computed_review_count", "computed_avg_rating",
            "featured", "hot_deal", "digital",
            "requires_measurement", "is_customisable",
            "sizes", "colors", "tags",
            "specifications", "faqs", "variants",
            # Phase 1 embeds
            "fabric", "measurement_guide", "shipping_profile",
            "status",
            "category_name", "category_slug", "sub_category_name",
            "brand_name", "brand_slug",
            "vendor",
            "commission_rate",
            # Phase 1 Product fields
            "weight_kg", "condition", "is_pre_order", "pre_order_date",
            "meta_title", "meta_description", "age_group", "gender_target",
            "measurement_template",
            "created_at", "updated_at",
        ]

    def get_image_url(self, obj):
        if obj.image:
            url = str(obj.image.url)
            if "res.cloudinary.com" in url and "/upload/" in url:
                return url.replace("/upload/", "/upload/f_auto,q_auto/")
            return url
        return None

    def get_cover_image_url(self, obj):
        return self.get_image_url(obj)

    def get_category_name(self, obj):
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "name", None)

    def get_category_slug(self, obj):
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "slug", None)

    def get_sub_category_name(self, obj):
        category = obj.primary_sub_category if hasattr(obj, "primary_sub_category") else None
        return getattr(category, "name", None)

    def get_brand_name(self, obj):
        """Return no product brand because Brand is not a product relationship."""
        return None

    def get_brand_slug(self, obj):
        """Return no product brand because Brand is not a product relationship."""
        return None


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR WRITE  (create / update via service layer)
# ─────────────────────────────────────────────────────────────────────────────

class ProductWriteSerializer(serializers.ModelSerializer):
    """
    Input-only serializer for vendor product creation and updates.

    Validation runs here; persistence is done in the service layer.
    The view MUST call service.create_product(validated_data=serializer.validated_data)
    rather than calling serializer.save() directly.
    """
    sizes = ProductSizeAndMeasurementGuideSerializer(many=True, required=False)
    tags = ProductTagSerializer(many=True, required=False)
    variants = ProductVariantGalleryMediaSerializer(many=True, required=False)
    faqs = ProductFaqSerializer(many=True, required=False)
    specifications = ProductSpecificationSerializer(many=True, required=False)
    gallery = ProductVariantGalleryMediaSerializer(many=True, required=False)
    images = ProductTagSerializer(many=True, required=False)
    fabric = ProductFabricSerializer(many=True, required=False)
    shipping_profile = ProductShippingProfileSerializer(many=True, required=False)
    
    size_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductSizeAndMeasurementGuide.objects.all(),
        many=True,
        source="sizes",
        required=False,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductTag.objects.all(),
        many=True,
        source="tags",
        required=False,
    )
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="categories",
        required=True,
        allow_empty=False,
        help_text="One to fifteen catalog category IDs. Replaces the legacy single category FK.",
    )
    sub_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="sub_categories",
        required=False,
        allow_empty=True,
        help_text="Optional deeper category IDs for discovery facets.",
    )
    idempotency_key = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Client UUID for safe network retry. Server returns same product on duplicate key.",
    )
    measurement_template = serializers.CharField(
        max_length=120,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional reusable measurement template name to apply.",
    )

    class Meta:
        model = Product
        fields = [
            "title", "description",
            "price", "old_price", "currency", "shipping_amount",
            "stock_qty", "max_stock",
            "category_ids", "sub_category_ids",
            "size_ids", "tag_ids",
            "requires_measurement", "is_customisable",
            "hot_deal", "digital", "commission_rate",
            "weight_kg", "condition", "is_pre_order", "pre_order_date",
            "meta_title", "meta_description", "age_group", "gender_target",
            "measurement_template",
            "idempotency_key",
        ]

    def validate_price(self, value):
        if value < 5000:
            raise serializers.ValidationError("Price must be at least ₦5,000.00.")
        return value

    def validate_old_price(self, value):
        if value is not None and value < 5000:
            raise serializers.ValidationError("Old price must be at least ₦5,000.00.")
        return value

    def validate_stock_qty(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative.")
        return value

    def validate_commission_rate(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError("Commission rate must be between 0 and 100.")
        return value

    def validate(self, data):
        max_stock = data.get("max_stock")
        stock_qty = data.get("stock_qty", 0)
        if max_stock is not None and stock_qty > max_stock:
            raise serializers.ValidationError(
                {"stock_qty": "Stock quantity cannot exceed max_stock ceiling."}
            )
        categories = data.get("categories") or []
        if not (1 <= len(categories) <= 15):
            raise serializers.ValidationError(
                {"category_ids": "Select at least 1 and at most 15 categories."}
            )
        sub_categories = data.get("sub_categories") or []
        if len(sub_categories) > 15:
            raise serializers.ValidationError(
                {"sub_category_ids": "Select at most 15 sub-categories."}
            )
        return data


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN SERIALIZER  (full status access)
# ─────────────────────────────────────────────────────────────────────────────

class ProductWriteFullSerializer(serializers.ModelSerializer):
    """
        Enterprise vendor create/update with NESTED variant write.

        Accepts a `variants` array so a vendor can submit all SKUs in one
        HTTP call. Persistence is fully delegated to the service layer —
        callers MUST use service.create_product_full(validated_data) or
        service.update_product_full(product, validated_data) rather than
        serializer.save().
        Validation rules:
        - Price must be > 0.
        - categories must contain 1-15 catalog category IDs.
        - stock_qty ≤ max_stock (when both provided).
        - commission_rate in [0, 100].
        - Each nested variant SKU must be unique within the submission.
    """
    size_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductSizeAndMeasurementGuide.objects.all(),
        many=True,
        source="sizes",
        required=False,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductTag.objects.all(),
        many=True,
        source="tags",
        required=False,
    )
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="categories",
        required=True,
        allow_empty=False,
        help_text="One to fifteen catalog category IDs. Replaces the legacy single category FK.",
    )
    sub_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="sub_categories",
        required=False,
        allow_empty=True,
        help_text="Optional deeper category IDs for discovery facets.",
    )
    variants = ProductVariantGalleryMediaWriteSerializer(many=True, required=False)
    fabric = ProductFabricSerializer(required=False, allow_null=True)
    measurement_guide = ProductMeasurementGuideSerializer(many=True, required=False)
    shipping_profile = ProductShippingProfileSerializer(required=False, allow_null=True)
    idempotency_key = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Safe network-retry UUID. Server returns same product on duplicate.",
    )
    measurement_template = serializers.CharField(
        max_length=120,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional reusable measurement template name to apply.",
    )

    class Meta:
        model = Product
        fields = [
            "title", "description",
            "price", "old_price", "currency", "shipping_amount",
            "stock_qty", "max_stock",
            "category_ids", "sub_category_ids",
            "size_ids", "tag_ids",
            "requires_measurement", "is_customisable",
            "hot_deal", "digital", "commission_rate",
            # Phase 1 write fields
            "weight_kg", "condition", "is_pre_order", "pre_order_date",
            "meta_title", "meta_description", "age_group", "gender_target",
            "measurement_template",
            # Nested write
            "variants", "fabric", "measurement_guide", "shipping_profile",
            "idempotency_key",
        ]

    def to_internal_value(self, data):
        # Normalize gender_target for client compatibility
        if "gender_target" in data and isinstance(data["gender_target"], str):
            gender = data["gender_target"].lower().strip()
            if gender == "male":
                data = data.copy()
                data["gender_target"] = "men"
            elif gender == "female":
                data = data.copy()
                data["gender_target"] = "women"
        return super().to_internal_value(data)

    def validate_price(self, value):
        if value < 5000:
            raise serializers.ValidationError("Price must be at least ₦5,000.00.")
        return value

    def validate_old_price(self, value):
        if value is not None and value < 5000:
            raise serializers.ValidationError("Old price must be at least ₦5,000.00.")
        return value

    def validate_stock_qty(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative.")
        return value

    def validate_commission_rate(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError("Commission rate must be between 0 and 100.")
        return value

    def validate_variants(self, variants):
        """Ensure no duplicate SKUs within a single submission."""
        skus = [v.get("sku", "") for v in variants if v.get("sku")]
        if len(skus) != len(set(skus)):
            raise serializers.ValidationError("Each variant must have a unique SKU.")
        return variants

    def validate(self, data):
        max_stock = data.get("max_stock")
        stock_qty = data.get("stock_qty", 0)
        if max_stock is not None and stock_qty > max_stock:
            raise serializers.ValidationError(
                {"stock_qty": "Stock quantity cannot exceed max_stock ceiling."}
            )
        categories = data.get("categories") or []
        if not (1 <= len(categories) <= 15):
            raise serializers.ValidationError(
                {"category_ids": "Select at least 1 and at most 15 categories."}
            )
        sub_categories = data.get("sub_categories") or []
        if len(sub_categories) > 15:
            raise serializers.ValidationError(
                {"sub_category_ids": "Select at most 15 sub-categories."}
            )
        return data


class ProductAdminSerializer(ProductDetailSerializer):
    """Extends detail serializer with writable status for admin/moderator."""
    status = serializers.ChoiceField(choices=Product.ProductStatus.choices if hasattr(Product, 'ProductStatus') else [
        ("draft", "Draft"),
        ("pending", "Pending Review"),
        ("published", "Published"),
        ("archived", "Archived"),
        ("rejected", "Rejected"),
    ])
    idempotency_key = serializers.UUIDField(read_only=True)

    class Meta(ProductDetailSerializer.Meta):
        fields = ProductDetailSerializer.Meta.fields + ["idempotency_key"]


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY LOG
# ─────────────────────────────────────────────────────────────────────────────

class ProductInventoryLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductInventoryLog
        fields = [
            "id",
            "quantity_delta", "quantity_before", "quantity_after",
            "reason", "reference_id", "note",
            "actor_name",
            "created_at",
        ]

    def get_actor_name(self, obj):
        if not obj.actor:
            return "System"
        return getattr(obj.actor, "get_full_name", lambda: str(obj.actor))()


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST
# ─────────────────────────────────────────────────────────────────────────────

class ProductWishlistSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = ProductWishlist
        fields = ["id", "product", "created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# DRAFT SESSION SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

class ProductDraftSessionSerializer(serializers.ModelSerializer):
    draft_key = serializers.UUIDField(required=False, validators=[])

    class Meta:
        model = ProductDraftSession
        fields = [
            "id",
            "draft_key",
            "idempotency_key",
            "payload",
            "current_step",
            "status",
            "linked_product",
            "expires_at",
            "last_synced_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "expires_at",
            "last_synced_at",
        ]

