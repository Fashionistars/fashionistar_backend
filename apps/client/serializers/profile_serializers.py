# apps/client/serializers/profile_serializers.py
"""
Client Profile Serializers (DRF — sync endpoints).

Conventions:
  - Input serializers validate and sanitise incoming data.
  - Output serializers are read-only and expose the full profile.
  - Address serializers handle nested CRUD.
"""
from rest_framework import serializers

from apps.client.models import ClientProfile, ClientAddress


class ClientAddressSerializer(serializers.ModelSerializer):
    """Read/Write serializer for ClientAddress."""

    class Meta:
        model  = ClientAddress
        fields = [
            "id",
            "label",
            "full_name",
            "phone",
            "street_address",
            "city",
            "state",
            "country",
            "postal_code",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ClientProfileOutputSerializer(serializers.ModelSerializer):
    """
    Full read-only profile serializer — used in GET /profile/ responses.
    """
    user_email = serializers.SerializerMethodField()
    user_id    = serializers.SerializerMethodField()
    addresses  = serializers.SerializerMethodField()

    class Meta:
        model  = ClientProfile
        fields = [
            "id",
            "user_id",
            "user_email",
            "bio",
            "default_shipping_address",
            "state",
            "country",
            "preferred_size",
            "style_preferences",
            "favourite_colours",
            "total_orders",
            "total_spent_ngn",
            "is_profile_complete",
            "email_notifications_enabled",
            "sms_notifications_enabled",
            "created_at",
            "updated_at",
            "addresses",
        ]
        read_only_fields = fields

    def get_user_email(self, obj) -> str:
        return getattr(obj.user, "email", "") or ""

    def get_user_id(self, obj) -> str:
        return str(obj.user.pk)

    def get_addresses(self, obj) -> list:
        qs = ClientAddress.objects.filter(client=obj, is_deleted=False).order_by(
            "-is_default", "-created_at"
        )
        return ClientAddressSerializer(qs, many=True).data


class ClientProfileUpdateSerializer(serializers.Serializer):
    """
    Input-only serializer for PATCH /profile/ requests.

    All fields are optional — clients send only what they want to change.
    """
    SIZE_CHOICES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

    bio                          = serializers.CharField(max_length=500, required=False, allow_blank=True)
    default_shipping_address     = serializers.CharField(required=False, allow_blank=True)
    state                        = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country                      = serializers.CharField(max_length=100, required=False, allow_blank=True)
    preferred_size               = serializers.ChoiceField(choices=SIZE_CHOICES, required=False, allow_blank=True)
    style_preferences            = serializers.ListField(child=serializers.CharField(), required=False)
    favourite_colours            = serializers.ListField(child=serializers.CharField(), required=False)
    email_notifications_enabled  = serializers.BooleanField(required=False)
    sms_notifications_enabled    = serializers.BooleanField(required=False)


class AddressCreateSerializer(serializers.ModelSerializer):
    """Input serializer for POST /addresses/."""

    class Meta:
        model  = ClientAddress
        fields = [
            "label",
            "full_name",
            "phone",
            "street_address",
            "city",
            "state",
            "country",
            "postal_code",
            "is_default",
        ]
