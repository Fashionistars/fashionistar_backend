# apps/authentication/serializers/profile.py
"""
Profile Serializers — Enterprise Edition
==========================================

Serializers:
  - MeSerializer            : Exact shape for GET /api/v1/auth/me/ (MeView rehydration)
  - ProtectedUserSerializer : Safe read-only fields for public/protected profile reads
  - UserProfileSerializer   : Full profile serializer for self-update (PATCH /profile/me/)
  - UserSerializer          : Canonical alias → UserProfileSerializer

Response shape contract (MeSerializer):
  All fields exactly mirror the MeView response so that the frontend
  services / Zustand store never break on a schema change — if MeView
  is updated, only update MeSerializer. Views call the serializer;
  they never hand-craft dicts.

Null / blank rules (match model definition):
  • email       → null when not set (email-provider only)
  • phone       → null when not set (phone-provider only)
  • first_name  → "" (empty string) when not set
  • last_name   → "" (empty string) when not set
  • avatar      → null when not set; serialized as a full HTTPS URL string
  • member_id   → string (FASTAR000001) — always set after creation
  • date_joined → ISO-8601 string or null
"""

from rest_framework import serializers

from apps.authentication.models import UnifiedUser


# ══════════════════════════════════════════════════════════════════════
# SHARED CUSTOM FIELDS
# ══════════════════════════════════════════════════════════════════════


class PhoneField(serializers.Field):
    """
    Serialize PhoneNumberField → E.164 string OR null.

    PhoneNumberField stores a PhoneNumber object internally.
    Calling str() on it returns the E.164 string (e.g. "+2348012345678").
    Returns None when the field is empty / None.
    """

    def to_representation(self, value):
        if not value:
            return None
        return str(value)

    def to_internal_value(self, data):
        # Write path not needed for read-only MeSerializer;
        # UserProfileSerializer exposes phone as read_only anyway.
        return data


class AvatarURLField(serializers.Field):
    """
    Serialize FileField / URLField avatar → string URL or null.

    The model uses a plain FileField (stores Cloudinary HTTPS URL as text).
    Django's FileField.url raises ValueError when the file name is empty,
    so we guard against that and fall back to the raw ``name`` value.
    """

    def to_representation(self, value):
        if not value:
            return None
        # FileField: value is a FieldFile whose .name holds the URL string
        try:
            return value.url if hasattr(value, "url") else str(value)
        except (ValueError, AttributeError):
            # .url can raise ValueError when storage doesn't know the URL
            return str(value.name) if hasattr(value, "name") and value.name else None


# ══════════════════════════════════════════════════════════════════════
# ME SERIALIZER — Exact response shape for GET /api/v1/auth/me/
# ══════════════════════════════════════════════════════════════════════


class MeSerializer(serializers.ModelSerializer):
    """
    Serializes the authenticated user's profile for the /auth/me/ endpoint.

    This serializer's output shape is the authoritative contract between
    the backend and the frontend Zustand auth store (useAuthHydration).

    Field-by-field null/blank behaviour:
      user_id          → str (UUID)
      identifying_info → str (email or phone or fallback string)
      member_id        → str | null  (null only before first save race, practically never)
      email            → str | null  (null for phone-only accounts)
      phone            → str | null  (null for email-only accounts, E.164 format)
      first_name       → str         (empty string "" when not set — model blank=True)
      last_name        → str         (empty string "" when not set — model blank=True)
      role             → str         (choices: client | vendor | staff | admin | …)
      auth_provider    → str         (choices: email | phone | google)
      is_verified      → bool
      is_active        → bool
      is_staff         → bool
      avatar           → str | null  (full Cloudinary HTTPS URL or null)
      bio              → str         (empty string "" when not set)
      country          → str         (empty string "" when not set)
      state            → str         (empty string "" when not set)
      city             → str         (empty string "" when not set)
      address          → str         (empty string "" when not set)
      date_joined      → str | null  (ISO-8601 datetime string or null)
      last_login       → str | null  (ISO-8601 datetime string or null)
    """

    # Custom field serializers
    user_id = serializers.SerializerMethodField()
    phone = PhoneField(read_only=True)
    avatar = AvatarURLField(read_only=True)
    identifying_info = serializers.SerializerMethodField()

    # Blank → empty-string fields (model: blank=True, null=True)
    first_name = serializers.CharField(default="", allow_blank=True, read_only=True)
    last_name = serializers.CharField(default="", allow_blank=True, read_only=True)

    # Datetime fields — ISO-8601 format
    date_joined = serializers.DateTimeField(format="iso-8601", read_only=True)
    last_login = serializers.DateTimeField(format="iso-8601", read_only=True)

    class Meta:
        model = UnifiedUser
        fields = (
            # ── Identity ────────────────────────────────────────────────
            "user_id",  # str(uuid)
            "identifying_info",  # email or phone (for display/logging)
            "member_id",  # FASTAR000001
            "email",  # str | null
            "phone",  # str | null  (E.164)
            # ── Name ────────────────────────────────────────────────────
            "first_name",  # str  (empty when not set)
            "last_name",  # str  (empty when not set)
            # ── Access Control ───────────────────────────────────────────
            "role",  # str  (client | vendor | staff | …)
            "auth_provider",  # str  (email | phone | google)
            "is_verified",  # bool
            "is_active",  # bool
            "is_staff",  # bool
            # ── Profile / Location ───────────────────────────────────────
            "avatar",  # str | null  (Cloudinary URL)
            "bio",  # str  (empty when not set)
            "country",  # str  (empty when not set)
            "state",  # str  (empty when not set)
            "city",  # str  (empty when not set)
            "address",  # str  (empty when not set)
            # ── Timestamps ───────────────────────────────────────────────
            "date_joined",  # ISO-8601 | null
            "last_login",  # ISO-8601 | null
        )
        read_only_fields = fields
        ref_name = "AuthMe"

    def get_user_id(self, obj):
        """Return UUID as a plain string (matches MeView's str(user.id))."""
        return str(obj.id)

    def get_identifying_info(self, obj):
        """
        Return the primary identifier: email → phone → fallback string.
        Mirrors the model's identifying_info property.
        """
        return obj.identifying_info


# ══════════════════════════════════════════════════════════════════════
# PROTECTED USER SERIALIZER — Safe read-only profile (public/shared)
# ══════════════════════════════════════════════════════════════════════


class ProtectedUserSerializer(serializers.ModelSerializer):
    """
    Expose safe, non-sensitive user information for authenticated profile reads.

    Used by endpoints that share user data with other users or services.
    Never exposes: password, groups, permissions, auth_provider, is_staff,
    internal timestamps, or any security-sensitive field.

    Fields returned:
      user_id       → str (UUID)
      member_id     → str | null
      email         → str | null
      phone         → str | null  (E.164)
      first_name    → str
      last_name     → str
      role          → str
      is_verified   → bool
      is_active     → bool
      avatar        → str | null  (Cloudinary URL)
      bio           → str
      country       → str
      state         → str
      city          → str
      address       → str
      date_joined   → ISO-8601 | null
    """

    user_id = serializers.SerializerMethodField()
    phone = PhoneField(read_only=True)
    avatar = AvatarURLField(read_only=True)
    first_name = serializers.CharField(default="", allow_blank=True, read_only=True)
    last_name = serializers.CharField(default="", allow_blank=True, read_only=True)
    date_joined = serializers.DateTimeField(format="iso-8601", read_only=True)

    class Meta:
        model = UnifiedUser
        fields = (
            "user_id",
            "member_id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "role",
            "is_verified",
            "is_active",
            "avatar",
            "bio",
            "country",
            "state",
            "city",
            "address",
            "date_joined",
        )
        read_only_fields = fields
        ref_name = "AuthProtectedUser"

    def get_user_id(self, obj):
        return str(obj.id)


# ══════════════════════════════════════════════════════════════════════
# USER PROFILE SERIALIZER — Full editable profile (PATCH /profile/me/)
# ══════════════════════════════════════════════════════════════════════


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Full profile serializer for self-update (PATCH /api/v1/profile/me/).

    Read-only fields:
      id, member_id, email, phone, role, auth_provider,
      is_verified, is_active, is_staff, is_superuser,
      date_joined, last_login, password, groups, user_permissions

    Writable fields (matches PROFILE_EDITABLE_FIELDS in profile_service):
      first_name, last_name, bio, country, state, city, address, avatar

    Extra output fields (computed):
      user_id         → str(uuid)
      identifying_info → str
      phone_display   → E.164 string | null (read-only convenience field)
      avatar_url      → Cloudinary URL string | null
    """

    user_id = serializers.SerializerMethodField()
    identifying_info = serializers.SerializerMethodField()

    # Read-only display fields
    phone_display = PhoneField(source="phone", read_only=True)
    avatar_url = AvatarURLField(source="avatar", read_only=True)
    date_joined = serializers.DateTimeField(format="iso-8601", read_only=True)
    last_login = serializers.DateTimeField(format="iso-8601", read_only=True)

    # Writable name fields
    first_name = serializers.CharField(
        allow_blank=True, allow_null=True, required=False
    )
    last_name = serializers.CharField(allow_blank=True, allow_null=True, required=False)

    class Meta:
        model = UnifiedUser
        fields = (
            # ── Computed / Display ───────────────────────────────────────
            "user_id",
            "identifying_info",
            # ── Identity (read-only) ─────────────────────────────────────
            "id",
            "member_id",
            "email",
            "phone_display",
            "role",
            "auth_provider",
            # ── Status (read-only) ───────────────────────────────────────
            "is_verified",
            "is_active",
            "is_staff",
            # ── Editable profile fields ──────────────────────────────────
            "first_name",
            "last_name",
            "bio",
            "country",
            "state",
            "city",
            "address",
            "avatar",  # write: accept URL from Cloudinary webhook
            "avatar_url",  # read: always the full URL string
            # ── Timestamps (read-only) ───────────────────────────────────
            "date_joined",
            "last_login",
        )
        read_only_fields = (
            "id",
            "user_id",
            "identifying_info",
            "member_id",
            "email",
            "phone_display",
            "role",
            "auth_provider",
            "is_verified",
            "is_active",
            "is_staff",
            "is_superuser",
            "avatar_url",
            "date_joined",
            "last_login",
        )
        extra_kwargs = {
            "avatar": {"write_only": False, "required": False, "allow_null": True},
        }
        ref_name = "AuthUserProfile"

    def get_user_id(self, obj):
        return str(obj.id)

    def get_identifying_info(self, obj):
        return obj.identifying_info

    def to_representation(self, instance):
        """
        Post-process the representation:
          - Ensure first_name / last_name return "" not None
          - Ensure avatar field itself returns the URL string (not FieldFile)
        """
        ret = super().to_representation(instance)
        ret["first_name"] = ret.get("first_name") or ""
        ret["last_name"] = ret.get("last_name") or ""
        # avatar write field → coerce FieldFile to URL string in response
        if "avatar" in ret and hasattr(instance.avatar, "name"):
            ret["avatar"] = ret.get("avatar_url")
        return ret


# ── Canonical alias — backward-compatible for any import of UserSerializer ─────
UserSerializer = UserProfileSerializer
