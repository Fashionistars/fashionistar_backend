# apps/product/serializers/product_serializers.py
"""Enterprise DRF Serializers for the Product domain.

Ensures type safety, strict payload validation, and clean serialization of
the consolidated Product, Variant, Fabric, and Measurement Guide schemas.

Serializer hierarchy:
  ProductVendorMiniSerializer   — Tiny vendor card embedded in product
  ProductTagSerializer          — Flat taxonomy for metadata tagging
  ProductFabricSpecificationSerializer — Material and care instructions
  ProductSizeAndMeasurementGuideSerializer — Reusable/custom size charts
  ProductShippingProfileSerializer — Physical dimensions for shipping fallbacks
  ProductSpecificationSerializer — Dynamic key-value technical data
  ProductFaqSerializer          — Frequently asked questions
  ProductVariantGalleryMediaSerializer — Unified variant read schema
  ProductVariantGalleryMediaWriteSerializer — Variant write validation
  ProductListSerializer         — public catalog card (optimized payload)
  ProductDetailSerializer       — public PDP (full nested relationships)
  ProductWriteSerializer        — Vendor basic create/update schemas
  ProductWriteFullSerializer    — Complex bulk nested writes
  ProductAdminSerializer        — Moderator-privileged schema
  ProductInventoryLogSerializer — Immutable stock history ledger
  ProductWishlistSerializer     — Saved products list representation
  ProductDraftSessionSerializer — Stepper state recovery data
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Category
from apps.product.models import (
    Coupon,
    Product,
    ProductFabricSpecification,
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
# 1. ATOMIC TAXONOMY & METADATA SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductFabricSpecificationSerializer(serializers.ModelSerializer):
    """Serializer mapping fabric materials, care instructions, and organic status.

    Phase 1 metadata expansion displayed under product specifications on PDP.
    """

    class Meta:
        model = ProductFabricSpecification
        fields = [
            "fabric_type",
            "care_instructions",
            "is_organic",
            "is_vegan",
            "country_of_origin",
        ]
        read_only_fields = ["id"]


class ProductSizeAndMeasurementGuideSerializer(serializers.ModelSerializer):
    """Serializer for sizing structures and tailor measurement charts.

    Supports reading and writing both reusable templates and standalone product
    size definitions.
    """

    id = serializers.UUIDField(read_only=True)
    description = serializers.ChoiceField(
        choices=ProductSizeAndMeasurementGuide.DESCRIPTION_CHOICES,
        default="custom"
    )
    size_label = serializers.ChoiceField(
        choices=ProductSizeAndMeasurementGuide.SIZE_CHOICES,
        default="M"
    )

    class Meta:
        model = ProductSizeAndMeasurementGuide
        fields = [
            "id",
            "vendor",
            "name",
            "description",
            "is_default",
            "save_as_template",
            "size_label",
            "chest_cm",
            "waist_cm",
            "hip_cm",
            "length_cm",
            "shoulder_cm",
            "sleeve_cm",
            "inseam_cm",
            "foot_length_cm",
            "sort_order",
        ]
        read_only_fields = ["id"]


# Alias mapping for historical compatibility references across old services
ProductMeasurementGuideSerializer = ProductSizeAndMeasurementGuideSerializer


class ProductShippingProfileSerializer(serializers.ModelSerializer):
    """Serializer capturing physical dimensions and courier restrictions.

    Calculates volumetric shipping costs and applies fallback thresholds.
    """

    effective_free_shipping_threshold = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        source="effective_free_shipping_threshold",
    )

    class Meta:
        model = ProductShippingProfile
        fields = [
            "id",
            "weight_kg",
            "dimensions_cm",
            "length_cm",
            "width_cm",
            "height_cm",
            "is_fragile",
            "requires_signature",
            "restricted_countries",
            "free_shipping_threshold",
            "effective_free_shipping_threshold",
            "processing_days",
        ]
        read_only_fields = ["id", "effective_free_shipping_threshold"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. VENDOR METADATA EMBEDDED SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

class ProductVendorMiniSerializer(serializers.Serializer):
    """Lightweight read-only representation of the product's vendor.

    Designed to execute with zero extra database hits by drawing solely
    from pre-selected/pre-fetched vendor relation attributes.
    """

    id = serializers.UUIDField(source="vendor.id")
    store_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()

    def get_store_name(self, obj: Any) -> Optional[str]:
        """Dynamically extracts the correct name fallback for the store."""
        vendor = obj.vendor
        if not vendor:
            return None
        return (
            getattr(vendor, "store_name", None)
            or getattr(vendor, "business_name", None)
            or str(vendor)
        )

    def get_avatar_url(self, obj: Any) -> Optional[str]:
        """Resolves absolute CDN media asset URL for the vendor logo."""
        vendor = obj.vendor
        if not vendor:
            return None
        logo = getattr(vendor, "logo", None) or getattr(vendor, "avatar", None)
        return str(logo.url) if logo else None

    def get_slug(self, obj: Any) -> Optional[str]:
        """Resolves the routing slug string for vendor profile navigation."""
        vendor = obj.vendor
        return getattr(vendor, "store_slug", None) if vendor else None

    def get_is_verified(self, obj: Any) -> bool:
        """Determines if the vendor has completed KYC requirements."""
        vendor = obj.vendor
        return getattr(vendor, "is_verified", False) if vendor else False


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPATIBILITY & SUPPORT SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductSpecificationSerializer(serializers.ModelSerializer):
    """Serializer for key-value pair product data specifications."""

    class Meta:
        model = ProductSpecification
        fields = ["id", "specification_title", "specification_value"]


class ProductFaqSerializer(serializers.ModelSerializer):
    """Serializer mapping customer support questions to explicit answers."""

    class Meta:
        model = ProductFaq
        fields = ["id", "question", "answer"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. CONSOLIDATED VARIANT & MEDIA SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantGalleryMediaSerializer(serializers.ModelSerializer):
    """Consolidated read serializer for product variants and gallery assets.

    Maps SKU details alongside respective sizing records, color keys,
    pricing adjustments, and dynamic Cloudinary asset transformations.
    """

    effective_price = serializers.ReadOnlyField()
    size = ProductSizeAndMeasurementGuideSerializer(read_only=True)
    media_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    video_thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariantGalleryMedia
        fields = [
            "id",
            "sku",
            "size",
            "color_name",
            "color_hex",
            "effective_price",
            "stock_qty",
            "barcode",
            "media_url",
            "thumbnail_url",
            "media_type",
            "alt_text",
            "ordering",
            "is_primary",
            "video_thumbnail_url",
            "duration_sec",
        ]

    def get_media_url(self, obj: ProductVariantGalleryMedia) -> Optional[str]:
        """Returns the secure path of the main media file."""
        return str(obj.media.url) if obj.media else None

    def get_thumbnail_url(self, obj: ProductVariantGalleryMedia) -> Optional[str]:
        """Returns a compressed thumbnail image path optimized for client-side lists."""
        if not obj.media or obj.media_type != "image":
            return None
        url = str(obj.media.url)
        if "res.cloudinary.com" in url:
            return url.replace("/upload/", "/upload/w_400,h_400,c_fill,f_auto,q_auto/")
        return url

    def get_video_thumbnail_url(self, obj: ProductVariantGalleryMedia) -> Optional[str]:
        """Returns the fallback image path for video assets."""
        return str(obj.video_thumbnail.url) if obj.video_thumbnail else None


class ProductVariantGalleryMediaWriteSerializer(serializers.ModelSerializer):
    """Nested write serializer validating variant creations during product setups.

    Performs structural type checks on pricing and quantities.
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
            "color_name",
            "color_hex",
            "stock_qty",
            "barcode",
            "media",
            "media_type",
            "alt_text",
            "ordering",
            "is_primary",
            "video_thumbnail",
            "duration_sec",
        ]

    def validate_sku(self, value: str) -> str:
        """Validates that standard SKU structures are formatted correctly."""
        if not value or not value.strip():
            raise serializers.ValidationError("SKU designations cannot be blank.")
        return value.strip().upper()

    def validate_stock_qty(self, value: int) -> int:
        """Prevents negative physical stock values."""
        if value < 0:
            raise serializers.ValidationError("Stock quantities cannot be negative values.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# 5. PUBLIC CATALOG LIST SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

class ProductListSerializer(serializers.ModelSerializer):
    """Fast, read-only serializer designed for high-performance indexing.

    Excludes large text fields (like full descriptions and draft JSON payloads).
    Excludes all AI features and administrative scores to reduce transfer weight.
    """

    image_url = serializers.SerializerMethodField()
    discount_percentage = serializers.ReadOnlyField()
    category_name = serializers.SerializerMethodField()
    category_slug = serializers.SerializerMethodField()
    vendor_name = serializers.SerializerMethodField()
    vendor_slug = serializers.SerializerMethodField()
    computed_review_count = serializers.IntegerField(read_only=True, default=0)
    computed_avg_rating = serializers.FloatField(read_only=True, default=0)
    sizes = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "slug",
            "sku",
            "price",
            "old_price",
            "discount_percentage",
            "currency",
            "image_url",
            "in_stock",
            "stock_qty",
            "featured",
            "hot_deal",
            "rating",
            "review_count",
            "computed_review_count",
            "computed_avg_rating",
            "category_name",
            "category_slug",
            "vendor_name",
            "vendor_slug",
            "requires_measurement",
            "is_customisable",
            "sizes",
            "colors",
            "created_at",
        ]

    def get_image_url(self, obj: Product) -> Optional[str]:
        """Resolves the default thumbnail image from the nested gallery."""
        primary_media = obj.product_variants_gallery_media.filter(
            is_primary=True, is_deleted=False
        ).first() or obj.product_variants_gallery_media.filter(
            is_deleted=False
        ).first()

        if primary_media and primary_media.media:
            url = str(primary_media.media.url)
            if "res.cloudinary.com" in url and "/upload/" in url:
                return url.replace("/upload/", "/upload/w_480,h_480,c_fill,f_auto,q_auto/")
            return url
        return None

    def get_vendor_name(self, obj: Product) -> Optional[str]:
        """Extracts the display name of the storefront."""
        if not obj.vendor:
            return None
        return (
            getattr(obj.vendor, "store_name", None)
            or getattr(obj.vendor, "business_name", None)
            or str(obj.vendor)
        )

    def get_vendor_slug(self, obj: Product) -> Optional[str]:
        """Extracts the routing identifier slug for the storefront."""
        return getattr(obj.vendor, "store_slug", None) if obj.vendor else None

    def get_category_name(self, obj: Product) -> Optional[str]:
        """Extracts the title of the primary categorization folder."""
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "name", None)

    def get_category_slug(self, obj: Product) -> Optional[str]:
        """Extracts the path slug of the primary categorization folder."""
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "slug", None)

    def get_sizes(self, obj: Product) -> List[Dict[str, Any]]:
        """Collects unique sizing specifications associated with this design."""
        variants = obj.product_variants_gallery_media.filter(is_deleted=False).select_related("size")
        sizes_list = []
        seen_size_ids = set()
        for variant in variants:
            if variant.size and variant.size.id not in seen_size_ids:
                seen_size_ids.add(variant.size.id)
                sizes_list.append(variant.size)
        return ProductSizeAndMeasurementGuideSerializer(sizes_list, many=True).data

    def get_colors(self, obj: Product) -> List[Dict[str, Any]]:
        """Collects unique color properties associated with this design."""
        return obj.color()


# ─────────────────────────────────────────────────────────────────────────────
# 6. PUBLIC DETAIL SERIALIZER (FULL PRODUCT DETAIL PAGE)
# ─────────────────────────────────────────────────────────────────────────────

class ProductDetailSerializer(serializers.ModelSerializer):
    """Full detail read representation of a Product.

    Excludes all system AI attributes (`ai_description`, `style_tags`,
    `occasion_tags`, `body_type_fit`, `ai_trend_score`, `search_vector`)
    and carbon/sustainability metrics to secure internal scoring and reduce
    payload sizes.
    """

    image_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()
    tags = ProductTagSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(
        many=True, read_only=True, source="product_specifications"
    )
    faqs = ProductFaqSerializer(many=True, read_only=True, source="product_faqs")
    variants = serializers.SerializerMethodField()
    fabric = ProductFabricSpecificationSerializer(
        read_only=True, source="product_fabric_specification"
    )
    measurement_guide = serializers.SerializerMethodField()
    shipping_profile = ProductShippingProfileSerializer(
        read_only=True, source="product_custom_shipping_profile"
    )
    category_name = serializers.SerializerMethodField()
    category_slug = serializers.SerializerMethodField()
    sub_category_name = serializers.SerializerMethodField()
    vendor = ProductVendorMiniSerializer(source="*", read_only=True)
    computed_review_count = serializers.IntegerField(read_only=True, default=0)
    computed_avg_rating = serializers.FloatField(read_only=True, default=0)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "slug",
            "sku",
            "description",
            "price",
            "old_price",
            "is_discounted",
            "discount_percentage",
            "discounted_price",
            "currency",
            "shipping_amount",
            "image_url",
            "cover_image_url",
            "gallery",
            "in_stock",
            "stock_qty",
            "max_stock",
            "views",
            "orders_count",
            "rating",
            "review_count",
            "computed_review_count",
            "computed_avg_rating",
            "featured",
            "hot_deal",
            "requires_measurement",
            "is_customisable",
            "sizes",
            "colors",
            "tags",
            "specifications",
            "faqs",
            "variants",
            "fabric",
            "measurement_guide",
            "shipping_profile",
            "status",
            "category_name",
            "category_slug",
            "sub_category_name",
            "vendor",
            "commission_rate",
            "weight_kg",
            "condition",
            "is_pre_order",
            "pre_order_date",
            "meta_title",
            "meta_description",
            "age_group",
            "gender_target",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj: Product) -> Optional[str]:
        """Resolves the default product image URL."""
        primary_media = obj.product_variants_gallery_media.filter(
            is_primary=True, is_deleted=False
        ).first() or obj.product_variants_gallery_media.filter(
            is_deleted=False
        ).first()

        if primary_media and primary_media.media:
            url = str(primary_media.media.url)
            if "res.cloudinary.com" in url and "/upload/" in url:
                return url.replace("/upload/", "/upload/f_auto,q_auto/")
            return url
        return None

    def get_cover_image_url(self, obj: Product) -> Optional[str]:
        """Alias property matching front-end rendering specifications."""
        return self.get_image_url(obj)

    def get_gallery(self, obj: Product) -> List[Dict[str, Any]]:
        """Collects and serializes all dynamic media assets in the gallery."""
        return ProductVariantGalleryMediaSerializer(obj.gallery(), many=True).data

    def get_sizes(self, obj: Product) -> List[Dict[str, Any]]:
        """Collects unique sizing specifications associated with this design."""
        variants = obj.product_variants_gallery_media.filter(is_deleted=False).select_related("size")
        sizes_list = []
        seen_size_ids = set()
        for variant in variants:
            if variant.size and variant.size.id not in seen_size_ids:
                seen_size_ids.add(variant.size.id)
                sizes_list.append(variant.size)
        return ProductSizeAndMeasurementGuideSerializer(sizes_list, many=True).data

    def get_colors(self, obj: Product) -> List[Dict[str, Any]]:
        """Collects unique colors associated with this design."""
        return obj.color()

    def get_variants(self, obj: Product) -> List[Dict[str, Any]]:
        """Maps child variants associated with this product."""
        return ProductVariantGalleryMediaSerializer(
            obj.product_variants_gallery_media.filter(is_deleted=False), many=True
        ).data

    def get_measurement_guide(self, obj: Product) -> List[Dict[str, Any]]:
        """Fetches sizing and measurement rules associated with this product."""
        # Fetches templates/measurement guidelines linked to this designer
        guides = ProductSizeAndMeasurementGuide.objects.filter(
            vendor=obj.vendor, is_default=True
        )
        return ProductSizeAndMeasurementGuideSerializer(guides, many=True).data

    def get_category_name(self, obj: Product) -> Optional[str]:
        """Extracts the display name of the primary classification folder."""
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "name", None)

    def get_category_slug(self, obj: Product) -> Optional[str]:
        """Extracts the path slug of the primary classification folder."""
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "slug", None)

    def get_sub_category_name(self, obj: Product) -> Optional[str]:
        """Extracts the display name of the sub-classification folder."""
        category = obj.primary_sub_category if hasattr(obj, "primary_sub_category") else None
        return getattr(category, "name", None)


# ─────────────────────────────────────────────────────────────────────────────
# 7. VENDOR DATA WRITE SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductWriteSerializer(serializers.ModelSerializer):
    """Input serializer validating parameters during standard product listings.

    Excludes internal attributes and delegates actual DB writes to the service.
    """

    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="categories",
        required=True,
        allow_empty=False,
    )
    sub_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="sub_categories",
        required=False,
        allow_empty=True,
    )
    idempotency_key = serializers.UUIDField(
        required=False, allow_null=True, write_only=True
    )

    class Meta:
        model = Product
        fields = [
            "title",
            "description",
            "price",
            "old_price",
            "currency",
            "shipping_amount",
            "stock_qty",
            "max_stock",
            "category_ids",
            "sub_category_ids",
            "requires_measurement",
            "is_customisable",
            "hot_deal",
            "condition",
            "is_pre_order",
            "pre_order_date",
            "meta_title",
            "meta_description",
            "age_group",
            "gender_target",
            "idempotency_key",
        ]

    def validate_price(self, value: Decimal) -> Decimal:
        """Validates that listing prices are within range requirements."""
        if value < 5000:
            raise serializers.ValidationError("Listing price must be at least ₦5,000.00.")
        return value

    def validate_old_price(self, value: Optional[Decimal]) -> Optional[Decimal]:
        """Validates that catalog retail comparison values are correct."""
        if value is not None and value < 5000:
            raise serializers.ValidationError("Legacy comparison price must be at least ₦5,000.00.")
        return value

    def validate_stock_qty(self, value: int) -> int:
        """Prevents negative physical inventory structures."""
        if value < 0:
            raise serializers.ValidationError("Listed inventory volume cannot be negative.")
        return value

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Performs logical consistency audits across listing fields."""
        max_stock = data.get("max_stock")
        stock_qty = data.get("stock_qty", 0)
        if max_stock is not None and stock_qty > max_stock:
            raise serializers.ValidationError(
                {"stock_qty": "Current catalog stock limits cannot exceed your maximum limits."}
            )

        categories = data.get("categories") or []
        if not (1 <= len(categories) <= 15):
            raise serializers.ValidationError(
                {"category_ids": "A design listing must be mapped to between 1 and 15 category folders."}
            )
        return data


class ProductWriteFullSerializer(serializers.ModelSerializer):
    """Serializer supporting nested product writes from the front-end wizard.

    Coordinates taxonomy links, custom measurement files, variants, and
    weight metrics in a single transactional payload.
    """

    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="categories",
        required=True,
        allow_empty=False,
    )
    sub_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="sub_categories",
        required=False,
        allow_empty=True,
    )
    variants = ProductVariantGalleryMediaWriteSerializer(many=True, required=False)
    fabric = ProductFabricSpecificationSerializer(required=False, allow_null=True)
    measurement_guide = ProductSizeAndMeasurementGuideSerializer(many=True, required=False)
    shipping_profile = ProductShippingProfileSerializer(required=False, allow_null=True)
    idempotency_key = serializers.UUIDField(
        required=False, allow_null=True, write_only=True
    )

    class Meta:
        model = Product
        fields = [
            "title",
            "description",
            "price",
            "old_price",
            "currency",
            "shipping_amount",
            "stock_qty",
            "max_stock",
            "category_ids",
            "sub_category_ids",
            "requires_measurement",
            "is_customisable",
            "hot_deal",
            "weight_kg",
            "condition",
            "is_pre_order",
            "pre_order_date",
            "meta_title",
            "meta_description",
            "age_group",
            "gender_target",
            "variants",
            "fabric",
            "measurement_guide",
            "shipping_profile",
            "idempotency_key",
        ]

    def to_internal_value(self, data: Any) -> Dict[str, Any]:
        """Normalizes external variables into internal designations."""
        if isinstance(data, dict) and "gender_target" in data:
            gender = str(data["gender_target"]).lower().strip()
            if gender == "male":
                data = data.copy()
                data["gender_target"] = "men"
            elif gender == "female":
                data = data.copy()
                data["gender_target"] = "women"
        return super().to_internal_value(data)

    def validate_price(self, value: Decimal) -> Decimal:
        """Validates that listing prices are within range requirements."""
        if value < 5000:
            raise serializers.ValidationError("Listing price must be at least ₦5,000.00.")
        return value

    def validate_old_price(self, value: Optional[Decimal]) -> Optional[Decimal]:
        """Validates that catalog retail comparison values are correct."""
        if value is not None and value < 5000:
            raise serializers.ValidationError("Legacy comparison price must be at least ₦5,000.00.")
        return value

    def validate_stock_qty(self, value: int) -> int:
        """Prevents negative physical inventory structures."""
        if value < 0:
            raise serializers.ValidationError("Listed inventory volume cannot be negative.")
        return value

    def validate_variants(self, variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensures that variant SKUs within a single submission are unique."""
        skus = [v.get("sku", "") for v in variants if v.get("sku")]
        if len(skus) != len(set(skus)):
            raise serializers.ValidationError("Each item variation must specify a unique SKU identifier.")
        return variants

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Performs logical consistency audits across listing fields."""
        max_stock = data.get("max_stock")
        stock_qty = data.get("stock_qty", 0)
        if max_stock is not None and stock_qty > max_stock:
            raise serializers.ValidationError(
                {"stock_qty": "Current catalog stock limits cannot exceed your maximum limits."}
            )

        categories = data.get("categories") or []
        if not (1 <= len(categories) <= 15):
            raise serializers.ValidationError(
                {"category_ids": "A design listing must be mapped to between 1 and 15 category folders."}
            )
        return data


# ─────────────────────────────────────────────────────────────────────────────
# 8. ADMINISTRATIVE CONTROLS
# ─────────────────────────────────────────────────────────────────────────────

class ProductAdminSerializer(ProductDetailSerializer):
    """Privileged serializer allowing administrators to edit verification status.

    Includes explicit audit trails and unique idempotency keys.
    """

    status = serializers.ChoiceField(choices=Product.ProductStatus.choices)
    idempotency_key = serializers.UUIDField(read_only=True)

    class Meta(ProductDetailSerializer.Meta):
        fields = ProductDetailSerializer.Meta.fields + ["idempotency_key"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. INVENTORY AUDIT LEDGER
# ─────────────────────────────────────────────────────────────────────────────

class ProductInventoryLogSerializer(serializers.ModelSerializer):
    """Serializer mapping immutable stock ledger entries.

    Provides a comprehensive operational change history for tailors.
    """

    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductInventoryLog
        fields = [
            "id",
            "quantity_delta",
            "quantity_before",
            "quantity_after",
            "reason",
            "reference_id",
            "note",
            "actor_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj: ProductInventoryLog) -> str:
        """Resolves the user identity responsible for the adjustment."""
        if not obj.actor:
            return "System Engine"
        return getattr(obj.actor, "get_full_name", lambda: str(obj.actor))()


# ─────────────────────────────────────────────────────────────────────────────
# 10. SAVED PRODUCTS & PERSISTENCE LISTS
# ─────────────────────────────────────────────────────────────────────────────

class ProductWishlistSerializer(serializers.ModelSerializer):
    """Serializer mapping client saved list indicators."""

    product = ProductListSerializer(read_only=True)

    class Meta:
        model = ProductWishlist
        fields = ["id", "product", "created_at"]
        read_only_fields = fields


class ProductDraftSessionSerializer(serializers.ModelSerializer):
    """Serializer mapping stepper session persistence parameters.

    Ensures form recovery state is synchronized.
    """

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

