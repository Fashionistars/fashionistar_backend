# apps/authentication/serializers/profile.py
"""
Profile Serializers — ProtectedUserSerializer, UserProfileSerializer.

Part of the serializers/ folder split (Bug 9).
Previously in the monolithic serializers.py.
"""

from apps.authentication.models import UnifiedUser
from rest_framework import serializers


class ProtectedUserSerializer(serializers.ModelSerializer):
    """
    Expose only safe, non-sensitive user information.
    Used by the /me/ endpoint for authenticated profile reads.
    """
    class Meta:
        model = UnifiedUser
        fields = (
            "id", "email", "phone", "role",
            "is_active", "is_verified",
            "bio", "avatar", "country", "city", "state", "address",
        )
        ref_name = "AuthProtectedUser"


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Full profile serializer — all fields except internal/auth-only ones.
    Used by admin and self-update endpoints.
    """
    class Meta:
        model = UnifiedUser
        fields = "__all__"
        read_only_fields = (
            "id", "password", "last_login",
            "is_superuser", "is_staff",
            "groups", "user_permissions",
        )
        extra_kwargs = {"password": {"write_only": True}}


# Canonical alias — keeps backward compat for any import of UserSerializer
UserSerializer = UserProfileSerializer
