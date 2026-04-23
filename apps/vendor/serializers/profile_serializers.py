# apps/vendor/serializers/profile_serializers.py
"""
Vendor Profile Serializers (DRF — sync endpoints).

These serializers are used exclusively by the DRF sync views at /api/v1/vendor/.
For the async Ninja views, use the Pydantic schemas in apps/vendor/types/vendor_schemas.py.
"""
from rest_framework import serializers

from apps.vendor.models import VendorPayoutProfile, VendorProfile, VendorSetupState


class VendorSetupStateSerializer(serializers.ModelSerializer):
    completion_percentage = serializers.ReadOnlyField()

    class Meta:
        model  = VendorSetupState
        fields = [
            "current_step",
            "profile_complete",
            "bank_details",
            "id_verified",          # informational — KYC future sprint
            "first_product",
            "onboarding_done",
            "completion_percentage",
        ]
        read_only_fields = fields


class VendorCollectionSerializer(serializers.Serializer):
    """Minimal representation of a Collection linked to this vendor."""
    id    = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug  = serializers.SlugField(read_only=True)


class VendorProfileOutputSerializer(serializers.ModelSerializer):
    setup_state  = VendorSetupStateSerializer(read_only=True)
    collections  = VendorCollectionSerializer(many=True, read_only=True)
    user_id      = serializers.SerializerMethodField()
    user_email   = serializers.SerializerMethodField()

    class Meta:
        model  = VendorProfile
        fields = [
            "id",
            "user_id",
            "user_email",
            "store_name",
            "store_slug",
            "tagline",
            "description",
            "logo_url",
            "cover_url",
            "city",
            "state",
            "country",
            "whatsapp",
            "opening_time",
            "closing_time",
            "business_hours",
            "instagram_url",
            "tiktok_url",
            "twitter_url",
            "website_url",
            "collections",
            "total_products",
            "total_sales",
            "total_revenue",
            "average_rating",
            "review_count",
            "wallet_balance",
            "is_verified",
            "is_active",
            "is_featured",
            "setup_state",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_id(self, obj) -> str:
        return str(obj.user.pk)

    def get_user_email(self, obj) -> str:
        return getattr(obj.user, "email", "") or ""


class VendorProfileUpdateSerializer(serializers.Serializer):
    """Input-only serializer for PATCH /vendor/profile/."""
    store_name     = serializers.CharField(max_length=150, required=False, allow_blank=True)
    tagline        = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description    = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    logo_url       = serializers.URLField(required=False, allow_blank=True)
    cover_url      = serializers.URLField(required=False, allow_blank=True)
    city           = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state          = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country        = serializers.CharField(max_length=100, required=False, allow_blank=True)
    whatsapp       = serializers.CharField(max_length=20, required=False, allow_blank=True)
    opening_time   = serializers.TimeField(required=False, allow_null=True)
    closing_time   = serializers.TimeField(required=False, allow_null=True)
    business_hours = serializers.JSONField(required=False)
    instagram_url  = serializers.URLField(required=False, allow_blank=True)
    tiktok_url     = serializers.URLField(required=False, allow_blank=True)
    twitter_url    = serializers.URLField(required=False, allow_blank=True)
    website_url    = serializers.URLField(required=False, allow_blank=True)
    # List of Collections PKs — VendorService.update_profile() handles M2M .set()
    collection_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="IDs of Collections this store specialises in.",
    )


class VendorSetupSerializer(serializers.Serializer):
    """
    Minimal setup payload to create the first vendor profile.
    Called on the POST /vendor/setup/ endpoint.
    """
    store_name    = serializers.CharField(max_length=150)
    description   = serializers.CharField(max_length=2000)
    tagline       = serializers.CharField(max_length=200, required=False, allow_blank=True)
    logo_url      = serializers.URLField(required=False, allow_blank=True)
    cover_url     = serializers.URLField(required=False, allow_blank=True)
    city          = serializers.CharField(max_length=100)
    state         = serializers.CharField(max_length=100)
    country       = serializers.CharField(max_length=100, required=False, allow_blank=True, default="Nigeria")
    whatsapp      = serializers.CharField(max_length=20, required=False, allow_blank=True)
    instagram_url = serializers.URLField(required=False, allow_blank=True)
    tiktok_url    = serializers.URLField(required=False, allow_blank=True)
    twitter_url   = serializers.URLField(required=False, allow_blank=True)
    website_url   = serializers.URLField(required=False, allow_blank=True)
    collection_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )


class VendorPayoutDetailsSerializer(serializers.Serializer):
    """Input serializer for POST /vendor/payout/."""
    bank_name      = serializers.CharField(max_length=150)
    bank_code      = serializers.CharField(max_length=10, required=False, allow_blank=True)
    account_name   = serializers.CharField(max_length=200)
    account_number = serializers.CharField(
        max_length=20,
        help_text="Bank account number. Will be encrypted before storage.",
    )
    paystack_recipient_code = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )


class VendorTransactionPinSerializer(serializers.Serializer):
    """Input serializer for PIN set/verify endpoints."""
    pin = serializers.CharField(
        min_length=4, max_length=4,
        help_text="4-digit numeric payout confirmation PIN.",
    )

    def validate_pin(self, value: str) -> str:
        if not value.isdigit():
            raise serializers.ValidationError("PIN must be 4 numeric digits.")
        return value
