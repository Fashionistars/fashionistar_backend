# apps/vendor/serializers/profile_serializers.py
"""
Vendor Profile Serializers (DRF — sync endpoints).
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
            "id_verified",
            "first_product",
            "onboarding_done",
            "completion_percentage",
        ]
        read_only_fields = fields


class VendorProfileOutputSerializer(serializers.ModelSerializer):
    setup_state = VendorSetupStateSerializer(read_only=True)
    user_id     = serializers.SerializerMethodField()
    user_email  = serializers.SerializerMethodField()

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
            "instagram_url",
            "tiktok_url",
            "twitter_url",
            "website_url",
            "total_products",
            "total_sales",
            "total_revenue",
            "average_rating",
            "review_count",
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
    store_name    = serializers.CharField(max_length=150, required=False, allow_blank=True)
    tagline       = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description   = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    logo_url      = serializers.URLField(required=False, allow_blank=True)
    cover_url     = serializers.URLField(required=False, allow_blank=True)
    city          = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state         = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country       = serializers.CharField(max_length=100, required=False, allow_blank=True)
    instagram_url = serializers.URLField(required=False, allow_blank=True)
    tiktok_url    = serializers.URLField(required=False, allow_blank=True)
    twitter_url   = serializers.URLField(required=False, allow_blank=True)
    website_url   = serializers.URLField(required=False, allow_blank=True)


class VendorSetupSerializer(serializers.Serializer):
    """
    Minimal setup payload required to create the first vendor profile.
    """

    store_name = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=2000)
    tagline = serializers.CharField(max_length=200, required=False, allow_blank=True)
    logo_url = serializers.URLField(required=False, allow_blank=True)
    cover_url = serializers.URLField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True, default="Nigeria")
    instagram_url = serializers.URLField(required=False, allow_blank=True)
    tiktok_url = serializers.URLField(required=False, allow_blank=True)
    twitter_url = serializers.URLField(required=False, allow_blank=True)
    website_url = serializers.URLField(required=False, allow_blank=True)


class VendorPayoutDetailsSerializer(serializers.Serializer):
    """Input serializer for POST /vendor/payout/."""
    bank_name      = serializers.CharField(max_length=150)
    bank_code      = serializers.CharField(max_length=10, required=False, allow_blank=True)
    account_name   = serializers.CharField(max_length=200)
    account_number = serializers.CharField(
        max_length=20,
        help_text="Bank account number. Will be encrypted before storage.",
    )
    paystack_recipient_code = serializers.CharField(max_length=100, required=False, allow_blank=True)
