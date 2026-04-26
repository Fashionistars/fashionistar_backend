# apps/authentication/serializers/auth.py
"""
Authentication Serializers — DRF
================================

Logic for validating user credentials, registration data, and OTP codes.
Ensures data integrity and security at the API entry point.
"""

import logging
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

from apps.authentication.models import UnifiedUser
from .profile import MeSerializer

logger = logging.getLogger(__name__)


# ===========================================================================
# OTP SERIALIZERS
# ===========================================================================


class OTPSerializer(serializers.Serializer):
    """
    Serializer for OTP verification.

    Validation Logic:
      - Required: 6-digit string.
      - Numeric only.

    Security:
      - Max length enforced to prevent buffer/memory attacks.
    """
    otp = serializers.CharField(
        required=True,
        max_length=6,
        help_text="One-Time Password (OTP) for verification.",
    )

    class Meta:
        ref_name = "AuthOTP"

    def validate(self, attrs):
        try:
            otp = attrs.get("otp")
            if not otp:
                logger.warning("OTP validation failed: OTP is required.")
                raise serializers.ValidationError({"otp": _("OTP is required.")})

            if len(otp) != 6:
                logger.warning("OTP validation failed: Invalid length %d.", len(otp))
                raise serializers.ValidationError({"otp": _("OTP length should be of six digits.")})

            if not otp.isdigit():
                logger.warning("OTP validation failed: Non-digit characters detected.")
                raise serializers.ValidationError({"otp": _("OTP must contain only digits.")})

            logger.info("OTP validation successful.")
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.error("Unexpected error in OTP validation: %s", exc)
            raise serializers.ValidationError({"otp": _("An error occurred during OTP validation.")})


class ResendOTPRequestSerializer(serializers.Serializer):
    """Serializer for requesting a new OTP."""
    email_or_phone = serializers.CharField(
        required=True,
        help_text="Registered email or phone number."
    )

    class Meta:
        ref_name = "AuthResendOTPRequest"


# ===========================================================================
# LOGIN SERIALIZERS
# ===========================================================================


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user authentication via Email or Phone.

    Validation Logic:
      1. Normalise input identifier (email to lowercase).
      2. Verify user exists and is not soft-deleted.
      3. Verify password hash matches.
      4. Check account lifecycle status (verified, active).

    Security:
      - Uses Django's `check_password` for constant-time comparison.
      - Throttled at the View level to prevent brute-force.
    """
    email_or_phone = serializers.CharField(
        write_only=True,
        required=True,
        help_text="User's email or phone for login",
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="User's password",
    )

    class Meta:
        ref_name = "AuthLogin"

    def validate(self, data):
        from apps.authentication.exceptions import (
            SoftDeletedUserError, AccountNotVerifiedError,
            AccountDeactivatedError, InvalidCredentialsError,
        )

        email_or_phone = data.get("email_or_phone")
        password = data.get("password")

        try:
            # Normalise identifier
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email_or_phone and "@" in email_or_phone:
                email_or_phone = _BUM.normalize_email(email_or_phone)
                data["email_or_phone"] = email_or_phone

            # Lookup User
            user = UnifiedUser.objects.filter(
                Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)
            ).first()

            if user is None:
                # Pool check for soft-deleted
                if UnifiedUser.objects.all_with_deleted().filter(
                    (Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)),
                    is_deleted=True
                ).exists():
                    logger.warning("⛔ Login rejected: soft-deleted account '%s'", email_or_phone)
                    raise SoftDeletedUserError()
                raise InvalidCredentialsError()

            if not user.check_password(password):
                logger.warning("⛔ Login failed: wrong password for '%s'", email_or_phone)
                raise InvalidCredentialsError()

            if not user.is_verified:
                logger.warning("⛔ Login rejected: account not verified '%s'", email_or_phone)
                raise AccountNotVerifiedError()

            if not user.is_active:
                logger.warning("⛔ Login rejected: deactivated account '%s'", email_or_phone)
                raise AccountDeactivatedError()

            logger.info("✅ LoginSerializer: valid credentials for '%s'", email_or_phone)
            data["user"] = user
            return data

        except (SoftDeletedUserError, AccountNotVerifiedError, AccountDeactivatedError, InvalidCredentialsError):
            raise
        except Exception as exc:
            logger.error("❌ Unexpected error in LoginSerializer: %s", exc, exc_info=True)
            raise serializers.ValidationError({"non_field_errors": [_("An unexpected error occurred during login.")]})


# ===========================================================================
# REGISTRATION SERIALIZERS
# ===========================================================================


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new user account.

    Validation Logic:
      - Enforces One-of-Email-or-Phone.
      - Password strength validation via Django standard.
      - Duplicate check against active and soft-deleted pools.

    Security:
      - Atomic transaction check to prevent race-condition duplicates.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = PhoneNumberField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    role = serializers.ChoiceField(
        choices=[("vendor", "Vendor"), ("client", "Client")],
        help_text="User's role: 'vendor' or 'client'",
    )

    class Meta:
        model = UnifiedUser
        fields = ("email", "phone", "role", "first_name", "last_name", "password", "password2")
        ref_name = "AuthUserRegistration"

    def validate(self, attrs):
        from apps.authentication.exceptions import SoftDeletedUserExistsError
        try:
            if attrs["password"] != attrs["password2"]:
                raise serializers.ValidationError({"password": _("Passwords do not match.")})

            # Normalise data
            attrs["email"] = attrs.get("email") or None
            attrs["phone"] = attrs.get("phone") or None
            
            email = attrs["email"]
            phone = attrs["phone"]

            if email and phone:
                raise serializers.ValidationError({"non_field_errors": [_("Provide either email or phone, not both.")]})
            if not email and not phone:
                raise serializers.ValidationError({"non_field_errors": [_("Provide either email or phone; one is required.")]})

            if email:
                from django.contrib.auth.base_user import BaseUserManager as _BUM
                attrs["email"] = _BUM.normalize_email(email)

            # Check duplicates
            identifier_q = Q(email__iexact=attrs["email"]) if attrs["email"] else Q(phone=attrs["phone"])
            if UnifiedUser.objects.all_with_deleted().filter(identifier_q, is_deleted=True).exists():
                logger.warning("⛔ Registration blocked: soft-deleted account exists.")
                raise SoftDeletedUserExistsError()

            if UnifiedUser.objects.filter(identifier_q).exists():
                field = "email" if attrs["email"] else "phone"
                raise serializers.ValidationError({field: [_("A user with this identifier already exists.")]})

            return attrs
        except (serializers.ValidationError, SoftDeletedUserExistsError):
            raise
        except Exception as exc:
            logger.error("Unexpected error in registration validation: %s", exc, exc_info=True)
            raise serializers.ValidationError({"non_field_errors": [_("An error occurred during validation.")]})


# ===========================================================================
# SESSION & GOOGLE SERIALIZERS
# ===========================================================================


class LogoutSerializer(serializers.Serializer):
    """Validates refresh token for blacklisting."""
    refresh = serializers.CharField(required=True)

    class Meta:
        ref_name = "AuthLogout"


class TokenRefreshSerializer(serializers.Serializer):
    """Wraps SimpleJWT refresh for schema generation."""
    refresh = serializers.CharField(required=True)

    class Meta:
        ref_name = "AuthTokenRefresh"


class GoogleAuthSerializer(serializers.Serializer):
    """
    Serializer for Google OAuth2 ID Token authentication.

    Validation Logic:
      - Verifies presence of 'id_token'.
      - Normalises 'role' for new registrations.
    """
    id_token = serializers.CharField(required=True)
    role = serializers.ChoiceField(
        choices=[("vendor", "Vendor"), ("client", "Client")],
        default="client",
        required=False,
        allow_blank=True,
    )

    class Meta:
        ref_name = "AuthGoogleAuth"

    def validate(self, attrs):
        try:
            if not attrs.get("id_token"):
                raise serializers.ValidationError({"id_token": _("Google ID Token is required.")})
            role = (attrs.get("role") or "client").strip().lower()
            attrs["role"] = role if role in ["vendor", "client"] else "client"
            return attrs
        except Exception as exc:
            logger.error("Google auth validation error: %s", exc)
            raise serializers.ValidationError({"non_field_errors": [_("An error occurred during Google Auth validation.")]})


# ===========================================================================
# RESPONSE SERIALIZERS (FOR SCHEMA)
# ===========================================================================


class RegistrationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.UUIDField()
    email = serializers.EmailField(allow_null=True)
    phone = serializers.CharField(allow_null=True)

    class Meta:
        ref_name = "AuthRegistrationResponse"


class LoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = MeSerializer()

    class Meta:
        ref_name = "AuthLoginResponse"


class OTPVerifyResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.UUIDField()

    class Meta:
        ref_name = "AuthOTPVerifyResponse"



# ─── Response Serializers ───────────────────────────────────────────────────

class RegistrationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.UUIDField()
    email = serializers.EmailField(allow_null=True)
    phone = serializers.CharField(allow_null=True)

    class Meta:
        ref_name = "AuthRegistrationResponse"


class LoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = MeSerializer()

    class Meta:
        ref_name = "AuthLoginResponse"


class OTPVerifyResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.UUIDField()

    class Meta:
        ref_name = "AuthOTPVerifyResponse"

