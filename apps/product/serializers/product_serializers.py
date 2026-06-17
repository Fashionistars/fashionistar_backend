# apps/product/serializers/product_serializers.py
"""Synchronous write-only DRF Serializers for the Product domain.

Handles payload validation and structural mapping for write operations:
Create (POST), Update (PUT/PATCH), and Delete (DELETE) [1].

These serializers enforce transaction boundaries and execute security policy checks.
All data queries are routed through backend service layers to prevent race
conditions [1].
"""

from __future__ import annotations
from apps.product.models import ProductWishlist

from decimal import Decimal
from typing import Any, Dict, List, Optional
from rest_framework import serializers
from django.db import transaction

from apps.catalog.models import Category
from apps.product.models import (
    Product,
    ProductStatus,
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
    """Enforces parameter checks on custom tailor measurement templates.

    Accepts the flattened frontend form shape (size_label + measurement cm fields)
    and maps to the canonical model. name/description/is_default/save_as_template
    are given safe defaults so the frontend wizard does not need to send them.
    """

    # Make backend-only fields optional with sane defaults so the frontend
    # wizard payload can omit them without triggering validation errors.
    name = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    is_default = serializers.BooleanField(required=False, default=False)
    save_as_template = serializers.BooleanField(required=False, default=False)

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
    logistics, and variations in a single transactional payload.

    ─── Frontend ↔ Backend Payload Contract ────────────────────────────────────
    The frontend ProductBuilderFormValues schema differs from the backend model
    fields in several ways. ``to_internal_value`` bridges all these gaps:

    Frontend field               → Backend field / handling
    ─────────────────────────────────────────────────────────────────────────────
    cash_payment_mode            → coerce to valid CashPaymentMode choice
      "payment_before_delivery"  → "disabled"  (not a model choice — no COD)
      "payment_on_delivery"      → "cod"
      other unknown values       → "disabled"
    publish_intent               → status
      "draft"                    → "draft"
      "pending"                  → "pending"
      (any other)                → "draft"
    cover_image_public_id +      → variants[] list (processed below)
      gallery[]
    measurement_guide[]{         → measurement_guide[]{name, description,
      size_label, *_cm, ...}       size_label, *_cm, is_default, ...}
    faqs: ["uuid", ...]          → stripped (handled via FAQ service)
    courier_id                   → stripped (handled separately)
    cover_image_url              → stripped (frontend display only)
    is_discounted                → stripped (frontend display only)
    discount_percentage          → stripped (frontend display only)
    discounted_price             → stripped (frontend display only)
    shipping_amount              → shipping_amount on Product
    ─────────────────────────────────────────────────────────────────────────────
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
    # status is optional on creation (defaults to draft); vendor can request
    # pending review by passing publish_intent="pending" (mapped in to_internal_value).
    status = serializers.ChoiceField(
        choices=[(s.value, s.label) for s in ProductStatus],
        required=False,
        default=ProductStatus.PENDING,
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
            "age_group",
            "gender_target",
            "variants",
            "fabric",
            "measurement_guide",
            "shipping_profile",
            "idempotency_key",
        ]

    # ── Frontend-only fields that must be stripped before DRF validation ──────
    # These keys exist in the builder form but have no direct model column.
    _FRONTEND_ONLY_FIELDS = {
        # Media display helpers
        "cover_image_url",
        # Discount UI state (not stored on Product model)
        "is_discounted",
        "discount_percentage",
        "discounted_price",
        # Logistics reference (no FK on Product model — handled via ShippingProfile)
        "courier_id",
        # Fabric flat fields (nested into `fabric` dict below)
        "fabric_type",
        "fabric_care_instructions",
        "fabric_is_organic",
        "fabric_is_vegan",
        "fabric_country_of_origin",
        # Shipping flat fields (nested into `shipping_profile` dict below)
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
        # Cover image flat fields (composed into `variants` list below)
        "cover_image_public_id",
        "cover_image_sku",
        "cover_image_color_name",
        "cover_image_color_hex",
        "cover_image_size_id",
        # Gallery list (composed into `variants` list below)
        "gallery",
        # FAQ list (handled via ProductFaq service, not by this serializer)
        "faqs",
        # Publish intent (mapped to `status` below)
        "publish_intent",
    }

    def to_internal_value(self, data: Any) -> Dict[str, Any]:
        """Bridges the frontend form payload to backend model field expectations.

        Applies all field transformations before DRF validation runs so that
        every mapping concern is isolated and testable here.
        """
        import logging
        _log = logging.getLogger(__name__)

        if isinstance(data, dict):
            data = data.copy()

            # ── 1. publish_intent → status ────────────────────────────────────
            # The frontend wizard sends `publish_intent: "draft" | "pending"`.
            # Map this to the canonical ProductStatus value. Any unrecognised
            # value falls back to draft so we never accidentally publish early.
            publish_intent = data.pop("publish_intent", None)
            if publish_intent and "status" not in data:
                if publish_intent == "pending":
                    data["status"] = ProductStatus.PENDING
                else:
                    data["status"] = ProductStatus.DRAFT

            # ── 2. cash_payment_mode normalisation ────────────────────────────
            # The model CashPaymentMode enum now includes all real payment modes.
            # Any completely unrecognised value falls back to "disabled" for safety.
            VALID_CASH_MODES = {
                "disabled",
                "cod",
                "pay_at_shop",
                "payment_on_delivery",
                "payment_before_delivery",
                "part_payment_before_delivery",
                "allow_all",  # CashPaymentMode.ALLOW_ALL
            }
            if "cash_payment_mode" in data:
                cash_mode = data["cash_payment_mode"]
                if cash_mode not in VALID_CASH_MODES:
                    # Unknown / legacy value (e.g. old 'both') → safe fallback.
                    data["cash_payment_mode"] = "disabled"

            # ── 3. gender_target normalisation ───────────────────────────────
            if "gender_target" in data:
                gender = str(data["gender_target"]).lower().strip()
                if gender == "male":
                    data["gender_target"] = "men"
                elif gender == "female":
                    data["gender_target"] = "women"

            # ── 4. Build `variants` from cover_image + gallery ────────────────
            cover_public_id = data.get("cover_image_public_id", "")
            gallery = data.get("gallery") or []
            if cover_public_id or gallery:
                variants: list = []
                if cover_public_id:
                    cover_var: dict = {
                        "is_primary": True,
                        "media": cover_public_id,
                        "media_type": "image",
                        "alt_text": data.get("title", "") or "Cover Image",
                        "ordering": 0,
                    }
                    if data.get("cover_image_sku"):
                        cover_var["sku"] = data["cover_image_sku"]
                    if data.get("cover_image_color_name"):
                        cover_var["color_name"] = data["cover_image_color_name"]
                    if data.get("cover_image_color_hex"):
                        cover_var["color_hex"] = data["cover_image_color_hex"]
                    if data.get("cover_image_size_id"):
                        cover_var["size_id"] = data["cover_image_size_id"]
                    variants.append(cover_var)

                for idx, item in enumerate(gallery):
                    pub_id = item.get("public_id") if isinstance(item, dict) else None
                    if pub_id:
                        g_var: dict = {
                            "is_primary": False,
                            "media": pub_id,
                            "media_type": item.get("media_type", "image"),
                            "alt_text": (
                                item.get("alt_text") or data.get("title", "") or f"Gallery Item {idx + 1}"
                            ),
                            "ordering": item.get("ordering", idx + 1),
                        }
                        if item.get("sku"):
                            g_var["sku"] = item["sku"]
                        if item.get("color_name"):
                            g_var["color_name"] = item["color_name"]
                        if item.get("color_hex"):
                            g_var["color_hex"] = item["color_hex"]
                        if item.get("size_id"):
                            g_var["size_id"] = item["size_id"]
                        variants.append(g_var)

                data["variants"] = variants

            # ── 5. Build `fabric` dict from flat frontend fields ───────────────
            fabric_type = data.get("fabric_type", "")
            if fabric_type:
                data["fabric"] = {
                    "fabric_type": fabric_type,
                    "care_instructions": data.get("fabric_care_instructions", "machine_wash"),
                    "is_organic": data.get("fabric_is_organic", False),
                    "is_vegan": data.get("fabric_is_vegan", False),
                    "country_of_origin": data.get("fabric_country_of_origin", ""),
                }
            elif "fabric" not in data:
                data["fabric"] = None

            # ── 6. Build `shipping_profile` dict from flat frontend fields ─────
            weight_raw = data.get("weight_kg", "")
            try:
                weight_val = Decimal(str(weight_raw)) if weight_raw and weight_raw != "" else Decimal("0")
            except Exception:
                weight_val = Decimal("0")
            if weight_val > 0:
                data["shipping_profile"] = {
                    "weight_kg": weight_val,
                    "dimensions_cm": data.get("dimensions_cm"),
                    "length_cm": data.get("length_cm", 0),
                    "width_cm": data.get("width_cm", 0),
                    "height_cm": data.get("height_cm", 0),
                    "is_fragile": data.get("is_fragile", False),
                    "requires_signature": data.get("requires_signature", False),
                    "restricted_countries": data.get("restricted_countries", []),
                    "free_shipping_threshold": data.get("free_shipping_threshold") or None,
                    "processing_days": data.get("processing_days", 1),
                }
            elif "shipping_profile" not in data:
                data["shipping_profile"] = None

            # ── 7. Coerce nullable numeric / date fields from "" → None ────────
            for field in ["pre_order_date", "old_price", "max_stock"]:
                if data.get(field) == "":
                    data[field] = None

            # ── 8. Strip all frontend-only keys before DRF validation ──────────
            # Doing this LAST ensures earlier steps can still read these keys.
            for key in list(self._FRONTEND_ONLY_FIELDS):
                data.pop(key, None)

        _log.debug("ProductWriteFullSerializer.to_internal_value payload keys: %s", list(data.keys()))
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
    payload = serializers.JSONField(required=False, default=dict)

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


# ─────────────────────────────────────────────────────────────────────────────
# READ-ONLY SERIALIZERS (Phase 1 Realignment)
# ─────────────────────────────────────────────────────────────────────────────

class ProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = ["id", "name", "slug"]


class ProductFabricSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFabricSpecification
        fields = [
            "fabric_type",
            "care_instructions",
            "is_organic",
            "is_vegan",
            "country_of_origin",
        ]


class ProductSizeAndMeasurementGuideSerializer(serializers.ModelSerializer):
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


# Alias for compatibility
ProductMeasurementGuideSerializer = ProductSizeAndMeasurementGuideSerializer


class ProductShippingProfileSerializer(serializers.ModelSerializer):
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


class ProductVendorMiniSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="vendor.id")
    store_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()

    def get_store_name(self, obj: Any) -> Optional[str]:
        vendor = obj.vendor
        if not vendor:
            return None
        return getattr(vendor, "store_name", None) or getattr(vendor, "business_name", None) or str(vendor)

    def get_avatar_url(self, obj: Any) -> Optional[str]:
        vendor = obj.vendor
        if not vendor:
            return None
        logo = getattr(vendor, "logo", None) or getattr(vendor, "avatar", None)
        return str(logo.url) if logo else None

    def get_slug(self, obj: Any) -> Optional[str]:
        vendor = obj.vendor
        return getattr(vendor, "store_slug", None) if vendor else None

    def get_is_verified(self, obj: Any) -> bool:
        vendor = obj.vendor
        return getattr(vendor, "is_verified", False) if vendor else False


class ProductFaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFaq
        fields = ["id", "question", "answer"]


class ProductVariantGalleryMediaSerializer(serializers.ModelSerializer):
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
        return str(obj.media.url) if obj.media else None

    def get_thumbnail_url(self, obj: ProductVariantGalleryMedia) -> Optional[str]:
        if not obj.media or obj.media_type != "image":
            return None
        url = str(obj.media.url)
        if "res.cloudinary.com" in url:
            return url.replace("/upload/", "/upload/w_400,h_400,c_fill,f_auto,q_auto/")
        return url

    def get_video_thumbnail_url(self, obj: ProductVariantGalleryMedia) -> Optional[str]:
        return str(obj.video_thumbnail.url) if obj.video_thumbnail else None


class ProductListSerializer(serializers.ModelSerializer):
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
            # NOTE: sku removed from Product — now lives only on ProductVariantGalleryMedia
            "price",
            "old_price",
            "is_discounted",
            "discount_percentage",
            "discounted_price",
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
            "cash_payment_mode",
            "sizes",
            "colors",
            "condition",
            "gender_target",
            "age_group",
            "is_pre_order",
            "pre_order_date",
            "sustainability_score",
            "carbon_footprint_kg",
            "ai_trend_score",
            "created_at",
        ]

    def get_image_url(self, obj: Product) -> Optional[str]:
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
        if not obj.vendor:
            return None
        return getattr(obj.vendor, "store_name", None) or getattr(obj.vendor, "business_name", None) or str(obj.vendor)

    def get_vendor_slug(self, obj: Product) -> Optional[str]:
        return getattr(obj.vendor, "store_slug", None) if obj.vendor else None

    def get_category_name(self, obj: Product) -> Optional[str]:
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "name", None)

    def get_category_slug(self, obj: Product) -> Optional[str]:
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "slug", None)

    def get_sizes(self, obj: Product) -> List[Dict[str, Any]]:
        variants = obj.product_variants_gallery_media.filter(is_deleted=False).select_related("size")
        sizes_list = []
        seen_size_ids = set()
        for variant in variants:
            if variant.size and variant.size.id not in seen_size_ids:
                seen_size_ids.add(variant.size.id)
                sizes_list.append(variant.size)
        return ProductSizeAndMeasurementGuideSerializer(sizes_list, many=True).data

    def get_colors(self, obj: Product) -> List[Dict[str, Any]]:
        return obj.color()


class ProductDetailSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()
    tags = ProductTagSerializer(many=True, read_only=True)
    faqs = ProductFaqSerializer(many=True, read_only=True)
    variants = serializers.SerializerMethodField()
    fabric = ProductFabricSpecificationSerializer(
        read_only=True, source="product_fabric_specification"
    )
    measurement_guide = serializers.SerializerMethodField()
    shipping_profile = ProductShippingProfileSerializer(read_only=True)
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
            # NOTE: sku removed from Product — now lives only on ProductVariantGalleryMedia
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
            "cash_payment_mode",
            "sizes",
            "colors",
            "tags",
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
            "condition",
            "is_pre_order",
            "pre_order_date",
            "meta_title",
            "meta_description",
            "age_group",
            "gender_target",
            "sustainability_score",
            "carbon_footprint_kg",
            "ai_trend_score",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj: Product) -> Optional[str]:
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
        return self.get_image_url(obj)

    def get_gallery(self, obj: Product) -> List[Dict[str, Any]]:
        return ProductVariantGalleryMediaSerializer(obj.gallery(), many=True).data

    def get_sizes(self, obj: Product) -> List[Dict[str, Any]]:
        variants = obj.product_variants_gallery_media.filter(is_deleted=False).select_related("size")
        sizes_list = []
        seen_size_ids = set()
        for variant in variants:
            if variant.size and variant.size.id not in seen_size_ids:
                seen_size_ids.add(variant.size.id)
                sizes_list.append(variant.size)
        return ProductSizeAndMeasurementGuideSerializer(sizes_list, many=True).data

    def get_colors(self, obj: Product) -> List[Dict[str, Any]]:
        return obj.color()

    def get_variants(self, obj: Product) -> List[Dict[str, Any]]:
        return ProductVariantGalleryMediaSerializer(
            obj.product_variants_gallery_media.filter(is_deleted=False), many=True
        ).data

    def get_measurement_guide(self, obj: Product) -> List[Dict[str, Any]]:
        guides = ProductSizeAndMeasurementGuide.objects.filter(
            vendor=obj.vendor, is_default=True
        )
        return ProductSizeAndMeasurementGuideSerializer(guides, many=True).data

    def get_category_name(self, obj: Product) -> Optional[str]:
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "name", None)

    def get_category_slug(self, obj: Product) -> Optional[str]:
        category = obj.primary_category if hasattr(obj, "primary_category") else None
        return getattr(category, "slug", None)

    def get_sub_category_name(self, obj: Product) -> Optional[str]:
        category = obj.primary_sub_category if hasattr(obj, "primary_sub_category") else None
        return getattr(category, "name", None)


class ProductAdminSerializer(ProductDetailSerializer):
    status = serializers.ChoiceField(choices=ProductStatus.choices)
    idempotency_key = serializers.UUIDField(read_only=True)

    class Meta(ProductDetailSerializer.Meta):
        fields = ProductDetailSerializer.Meta.fields + ["idempotency_key"]


