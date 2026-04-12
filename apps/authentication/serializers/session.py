# apps/authentication/serializers/session.py
"""
Session & Login Event Serializers.

Provides validated, documented serializers for:
  - UserSession  (active sessions list, revoke)
  - LoginEvent   (security audit log / login activity)

These replace the raw-dict serialization previously done inline in
session_views/sync_views.py. Using proper serializers:
  ✅ Validates all request data (e.g. session_id format)
  ✅ Documented in Swagger/OpenAPI schema
  ✅ Type-safe, reusable across DRF & Ninja layers
  ✅ Single source of truth for API shape

Part of the Phase 5 serializers split (following the same naming
conventions as auth.py, otp.py, password.py, profile.py).
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.authentication.models import LoginEvent, UserSession


# ══════════════════════════════════════════════════════════════════════
# USER SESSION SERIALIZERS
# ══════════════════════════════════════════════════════════════════════


class UserSessionSerializer(serializers.ModelSerializer):
    """
    Read serializer for UserSession — used by the active sessions list.

    All UUID7 primary keys are serialized as strings (required for
    JavaScript, which cannot safely handle 128-bit integers).

    The ``is_current`` flag is computed dynamically at query time
    (via the view injecting the current JTI), so it is read-only here.

    The ``is_expired`` flag is a computed property (not stored in DB).
    """

    # UUID7 pk → always serialize as string for JavaScript safety
    id = serializers.CharField(source="pk", read_only=True)

    # Alias for consistency with frontend camelCase expectations
    browser = serializers.CharField(source="browser_family", read_only=True)
    os      = serializers.CharField(source="os_family", read_only=True)

    # ISO-8601 datetime strings
    created_at   = serializers.DateTimeField(read_only=True)
    last_used_at = serializers.DateTimeField(read_only=True)
    expires_at   = serializers.DateTimeField(allow_null=True, read_only=True)

    # Computed at serializer-init time — must be set via context
    is_current = serializers.SerializerMethodField()
    is_expired  = serializers.SerializerMethodField()

    class Meta:
        model  = UserSession
        fields = (
            "id",
            "device_name",
            "client_type",
            "browser",
            "os",
            "ip_address",
            "country",
            "city",
            "created_at",
            "last_used_at",
            "expires_at",
            "is_current",
            "is_expired",
        )
        read_only_fields = (
            "id", "device_name", "client_type", "browser", "os",
            "ip_address", "country", "city",
            "created_at", "last_used_at", "expires_at",
            "is_current", "is_expired",
        )
        ref_name = "UserSession"

    def get_is_current(self, obj: UserSession) -> bool:
        """
        True when the session's JTI matches the current request's access token JTI.

        The view must pass `current_jti` in serializer context:
            serializer = UserSessionSerializer(
                sessions, many=True, context={"current_jti": current_jti}
            )
        """
        current_jti = self.context.get("current_jti")
        if not current_jti:
            return False
        return obj.jti == current_jti

    def get_is_expired(self, obj: UserSession) -> bool:
        """True when the session's refresh token has expired."""
        if obj.expires_at is None:
            return False
        return obj.expires_at < timezone.now()


class UserSessionListSerializer(serializers.Serializer):
    """
    Response envelope for GET /api/v1/auth/sessions/

    Wraps the session list with count metadata for frontend pagination.
    """

    status  = serializers.CharField(default="success", read_only=True)
    count   = serializers.IntegerField(read_only=True)
    results = UserSessionSerializer(many=True, read_only=True)

    class Meta:
        ref_name = "UserSessionList"


class SessionRevokeRequestSerializer(serializers.Serializer):
    """
    Request serializer for DELETE /api/v1/auth/sessions/<session_id>/

    Validates that the session_id provided in the URL is a non-empty string.
    The actual UUID format validation happens at the DB query level.
    """

    session_id = serializers.CharField(
        min_length=1,
        max_length=100,
        help_text="UUID7 string of the session to revoke.",
    )

    class Meta:
        ref_name = "SessionRevokeRequest"


# ══════════════════════════════════════════════════════════════════════
# LOGIN EVENT SERIALIZERS
# ══════════════════════════════════════════════════════════════════════


class LoginEventSerializer(serializers.ModelSerializer):
    """
    Read serializer for LoginEvent — used by the login activity list.

    Analogous to Binance's "Login Activity" or Google's
    "Recent Security Events" dashboard panel.

    All UUID7 primary keys are serialized as strings.
    ``timestamp`` is an alias for ``created_at`` (audit-log convention).
    """

    # UUID7 pk → always serialize as string
    id = serializers.CharField(source="pk", read_only=True)

    # ISO-8601 alias (frontend convention for audit logs)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)

    # Flatten device info aliases for frontend consumption
    browser = serializers.CharField(source="browser_family", read_only=True)
    os      = serializers.CharField(source="os_family", read_only=True)

    class Meta:
        model  = LoginEvent
        fields = (
            "id",
            "outcome",
            "is_successful",
            "failure_reason",
            "auth_method",
            "ip_address",
            "country",
            "country_code",
            "city",
            "client_type",
            "browser",
            "os",
            "device_type",
            "risk_score",
            "is_new_device",
            "is_new_country",
            "is_tor_exit_node",
            "timestamp",
        )
        read_only_fields = fields
        ref_name = "LoginEvent"


class LoginEventListSerializer(serializers.Serializer):
    """
    Response envelope for GET /api/v1/auth/login-events/

    Wraps the events list with count metadata.
    """

    status  = serializers.CharField(default="success", read_only=True)
    count   = serializers.IntegerField(read_only=True)
    results = LoginEventSerializer(many=True, read_only=True)

    class Meta:
        ref_name = "LoginEventList"
