# apps/authentication/admin_backend/serializers.py
"""
DRF write serializers for the authentication admin API.

These serializers are used exclusively on DRF sync mutation views
(POST/PATCH/DELETE). Read serialization is handled by the Ninja schemas
in schemas.py.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Partial update serializer for admin user management.

    Only staff-editable fields are exposed. Protected fields
    (email, phone, role, auth_provider, member_id) are read-only
    to enforce model-level immutability via the admin API.
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "bio",
            "country",
            "state",
            "city",
            "address",
            "is_active",
            "is_verified",
            "is_staff",
        ]
        # Protected immutable fields — admin mutation is done via
        # dedicated service methods (suspend, reactivate, verify, role_update)
        read_only_fields = [
            "email",
            "phone",
            "role",
            "auth_provider",
            "member_id",
            "is_superuser",
            "date_joined",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """Prevent setting is_superuser via this serializer."""
        if "is_superuser" in attrs:
            raise serializers.ValidationError(
                {"is_superuser": "Superuser status cannot be changed via this API."}
            )
        return super().validate(attrs)


class AdminUserSuspendSerializer(serializers.Serializer):
    """Request body validator for the suspend user action."""
    reason = serializers.CharField(
        min_length=5,
        max_length=500,
        help_text="Reason for suspension (displayed in audit trail).",
    )


class AdminUserForcePasswordSerializer(serializers.Serializer):
    """Request body validator for force-reset password (superuser only)."""
    new_password = serializers.CharField(
        min_length=8,
        max_length=128,
        write_only=True,
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        min_length=8,
        max_length=128,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs


class AdminUserRoleUpdateSerializer(serializers.Serializer):
    """Request body validator for role update (superuser only)."""
    new_role = serializers.ChoiceField(
        choices=User.ROLE_CHOICES,
        help_text="The new RBAC role to assign to this user.",
    )
