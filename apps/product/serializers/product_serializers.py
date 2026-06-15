# apps/product/serializers/product_serializers.py
"""Synchronous write-only DRF Serializers for the Product domain.

Handles payload validation and structural mapping for write operations:
Create (POST), Update (PUT/PATCH), and Delete (DELETE) [1].

These serializers enforce transaction boundaries and execute security policy checks.
All data queries are routed through backend service layers to prevent race
conditions [1].
"""

from apps.product.models import ProductWishlist
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional
from rest_framework import serializers
from django.db import transaction

from apps.catalog.models import Category
from apps.product.models import (
    Product,
    ProductFabricSpecification,
    ProductSizeAndMeasurementGuide,
    ProductFaq,
    ProductVariantGalleryMedia,
    ProductTag,
    ProductReview,
    ProductInventoryLog,
    ProductDraftSession,
    ProductShippingProfile,
)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: WRITE-ONLY SYSTEM BOUNDARY SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductTagWriteSerializer(serializers.ModelSerializer):
    """Enforces taxonomy parameters and write validation rules for tags."""

    class Meta:
        model = ProductTag
        fields = ["name"]

    def validate_name(self, value: str) -> str:
        """Enforces clean string normalization for category categorization."""
        clean_val = value.strip()
        if len(clean_val) < 2:
            raise serializers.ValidationError("Tag identifiers must contain at least 2 characters.")
        return clean_val


class ProductFabricSpecificationWriteSerializer(serializers.ModelSerializer):
    """Validates fabric specifications during nested product listing."""

    class Meta:
        model = ProductFabricSpecification
        fields = [
            "fabric_type",
            "care_instructions",
            "is_organic",
            "is_vegan",
            "country_of_origin",
        ]


class ProductSizeAndMeasurementGuideWriteSerializer(serializers.ModelSerializer):
    """Enforces parameter checks on custom tailor measurement templates [1]."""

    class Meta:
        model = ProductSizeAndMeasurementGuide
        fields = [
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

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates that custom measurement values are correctly defined."""
        if data.get("description") == "measurement":
            required_params = ["chest_cm", "waist_cm", "length_cm"]
            for field in required_params:
                if not data.get(field):
                    raise serializers.ValidationError(
                        {field: "This measurement parameters is required for custom-fitted designs."}
                    )
        return data


class ProductShippingProfileWriteSerializer(serializers.ModelSerializer):
    """Enforces volumetric checks on shipping sizes and weights."""

    class Meta:
        model = ProductShippingProfile
        fields = [
            "weight_kg",
            "dimensions_cm",
            "length_cm",
            "width_cm",
            "height_cm",
            "is_fragile",
            "requires_signature",
            "restricted_countries",
            "free_shipping_threshold",
            "processing_days",
        ]

    def validate_weight_kg(self, value: Decimal) -> Decimal:
        """Prevents zero-weight entries on logical packages."""
        if value <= 0:
            raise serializers.ValidationError("Volumetric shipping packages must weigh more than 0kg.")
        return value


class ProductFaqWriteSerializer(serializers.ModelSerializer):
    """Validates embedded FAQ entries within product listings."""

    class Meta:
        model = ProductFaq
        fields = ["question", "answer"]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: NESTED VARIANT WRITE SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantGalleryMediaWriteSerializer(serializers.ModelSerializer):
    """Validates variants and Cloudinary uploads within single write payloads [1]."""

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
            "media",
            "media_type",
            "alt_text",
            "ordering",
            "is_primary",
            "video_thumbnail",
            "duration_sec",
            "barcode",
        ]

    def validate_stock_qty(self, value: int) -> int:
        """Enforces logical limit parameters for stock volumes."""
        if value < 0:
            raise serializers.ValidationError("Listed inventory limits cannot be negative values.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: CORE PRODUCT WRITE SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductWriteSerializer(serializers.ModelSerializer):
    """Validates core base fields for basic product modifications."""

    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="categories",
        required=True,
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
            "cash_payment_mode",
            "is_pre_order",
            "pre_order_date",
            "status",
            "featured",
            "hot_deal",
            "condition",
            "meta_title",
            "meta_description",
            "gender_target",
            "age_group",
            "idempotency_key",
        ]

    def validate_price(self, value: Decimal) -> Decimal:
        """Enforces minimum floor pricing limits."""
        if value < 5000:
            raise serializers.ValidationError("Catalog pricing must stand at ₦5,000.00 or higher.")
        return value


class ProductWriteFullSerializer(serializers.ModelSerializer):
    """Coordinating serializer for nested product writes from the wizard stepper.

    Validates taxonomy links, fabric records, custom measurements,
    logistics, and variations in a single transactional payload [1].
    """

    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="categories",
        required=True,
    )
    sub_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        source="sub_categories",
        required=False,
    )
    variants = ProductVariantGalleryMediaWriteSerializer(many=True, required=False)
    fabric = ProductFabricSpecificationWriteSerializer(required=False, allow_null=True)
    measurement_guide = ProductSizeAndMeasurementGuideWriteSerializer(many=True, required=False)
    shipping_profile = ProductShippingProfileWriteSerializer(required=False, allow_null=True)

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
            "cash_payment_mode",
            "is_pre_order",
            "pre_order_date",
            "status",
            "featured",
            "hot_deal",
            "condition",
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
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

    """Enforces validation checks on customer reviews."""

    class Meta:
        model = ProductReview
        fields = ["product", "rating", "review", "idempotency_key"]

    def validate_rating(self, value: int) -> int:
        """Enforces star review scoring limits."""
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Scores must stand between 1 and 5 stars.")
        return value



    """Enforces parameters for direct inventory adjustments."""


class ProductInventoryLogSerializer(serializers.ModelSerializer):
    """Serializer mapping immutable stock ledger entries.

    Provides a comprehensive operational change history for tailors.
    """

    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductInventoryLog
        fields = ["product", "variant", "quantity_delta", "reason", "reference_id", "note", "actor_name"]
        read_only_fields = ["actor_name", "reference_id"]


    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prevents zero-impact adjustments from cluttering database history."""
        if data.get("quantity_delta") == 0:
            raise serializers.ValidationError(
                {"quantity_delta": "Inventory adjustments must specify a non-zero change value."}
            )
        return data
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

    product = ProductWriteSerializer(read_only=True)

    class Meta:
        model = ProductWishlist
        fields = ["id", "product", "created_at"]
        read_only_fields = fields


class ProductDraftSessionSerializer(serializers.ModelSerializer):
    """Serializer mapping stepper session persistence parameters.

    Ensures form recovery state is synchronized.
    """

    draft_key = serializers.UUIDField(required=False, validators=[])





# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: LEDGERS & CUSTOMER REVIEW TRACKERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductDraftSessionWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating product draft sessions."""
    payload = ProductWriteFullSerializer()

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

