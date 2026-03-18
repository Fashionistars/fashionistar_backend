# apps/authentication/serializers/auth.py
"""
Auth Serializers — Login, Registration, Logout, Token Refresh, Google OAuth.

Part of the serializers/ folder split (Bug 9).
Previously in the monolithic serializers.py.
"""

import logging

from apps.authentication.models import UnifiedUser
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

logger = logging.getLogger(__name__)


# ─── OTP Serializers ────────────────────────────────────────────────────────

class OTPSerializer(serializers.Serializer):
    """
    Serializer for OTP verification with robust validation and error handling.
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
                raise serializers.ValidationError(
                    {"otp": _("OTP length should be of six digits.")}
                )

            if not otp.isdigit():
                logger.warning("OTP validation failed: Non-digit characters detected.")
                raise serializers.ValidationError(
                    {"otp": _("OTP must contain only digits.")}
                )

            logger.info("OTP validation successful.")
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.error("Unexpected error in OTP validation: %s", exc)
            raise serializers.ValidationError(
                {"otp": _("An error occurred during OTP validation.")}
            )


class AsyncOTPSerializer(OTPSerializer):
    """Asynchronous version of OTPSerializer."""

    async def avalidate(self, attrs):
        return self.validate(attrs)


# ─── Login Serializers ───────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    """
    Serializer for authenticating users with either email or phone.

    Enterprise-grade auth flow (priority order):

    1. Alive-only lookup (is_deleted=False)
    2. Soft-deleted pool check → SoftDeletedUserError (403)
    3. Password check → InvalidCredentialsError (401)
    4a. is_verified check FIRST → AccountNotVerifiedError (403) with OTP URLs
    4b. is_active check SECOND → AccountDeactivatedError (403) with support URL
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
            SoftDeletedUserError,
            AccountNotVerifiedError,
            AccountDeactivatedError,
            InvalidCredentialsError,
        )

        email_or_phone = data.get("email_or_phone")
        password       = data.get("password")

        try:
            # ── Step 1: Alive-only lookup ─────────────────────────────────
            if "@" in email_or_phone:
                user = UnifiedUser.objects.filter(email=email_or_phone).first()
            else:
                user = UnifiedUser.objects.filter(phone=email_or_phone).first()

            if user is None:
                # ── Step 2: Soft-deleted pool check ───────────────────────
                if "@" in email_or_phone:
                    deleted_user = UnifiedUser.objects.all_with_deleted().filter(
                        email=email_or_phone, is_deleted=True,
                    ).first()
                else:
                    deleted_user = UnifiedUser.objects.all_with_deleted().filter(
                        phone=email_or_phone, is_deleted=True,
                    ).first()

                if deleted_user:
                    logger.warning(
                        "⛔ Login rejected: soft-deleted account '%s'", email_or_phone
                    )
                    raise SoftDeletedUserError()

                logger.warning("⛔ Login failed: user not found '%s'", email_or_phone)
                raise InvalidCredentialsError()

            # ── Step 3: Password check ────────────────────────────────────
            if not user.check_password(password):
                logger.warning(
                    "⛔ Login failed: wrong password for '%s'", email_or_phone
                )
                raise InvalidCredentialsError()

            # ── Step 4a: OTP verification (FIRST — before is_active) ──────
            if not user.is_verified:
                logger.warning(
                    "⛔ Login rejected: account not verified '%s'", email_or_phone
                )
                raise AccountNotVerifiedError()

            # ── Step 4b: Admin deactivation (SECOND) ─────────────────────
            if not user.is_active:
                logger.warning(
                    "⛔ Login rejected: deactivated account '%s'", email_or_phone
                )
                raise AccountDeactivatedError()

            logger.info(
                "✅ LoginSerializer: valid credentials for '%s'", email_or_phone
            )
            data["user"] = user
            return data

        except (
            SoftDeletedUserError, AccountNotVerifiedError,
            AccountDeactivatedError, InvalidCredentialsError,
        ):
            raise
        except Exception as exc:
            logger.error(
                "❌ Unexpected error in LoginSerializer.validate(): %s",
                exc, exc_info=True,
            )
            raise serializers.ValidationError(
                {"non_field_errors": [_("An unexpected error occurred during login.")]}
            )


class AsyncLoginSerializer(LoginSerializer):
    """Asynchronous version of LoginSerializer."""

    async def avalidate(self, data):
        return self.validate(data)


# ─── Registration Serializers ─────────────────────────────────────────────────

class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration (email or phone).
    Strictly enforces One-of-Email-or-Phone logic.
    Delegates creation to RegistrationService.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
        help_text="User's password",
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Confirm user's password",
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        help_text="User's email address",
    )
    phone = PhoneNumberField(
        required=False,
        allow_blank=True,
        help_text="User's phone number",
    )

    ROLE_CHOICES = [("vendor", "Vendor"), ("client", "Client")]
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
        help_text="User's role: 'vendor' or 'client'",
    )

    class Meta:
        model = UnifiedUser
        fields = ("email", "phone", "role", "password", "password2")
        ref_name = "AuthUserRegistration"

    def validate(self, attrs):
        try:
            if attrs["password"] != attrs["password2"]:
                logger.warning("Registration failed: Passwords do not match.")
                raise serializers.ValidationError(
                    {"password": _("Passwords do not match.")}
                )

            # Normalise empty strings → None
            attrs["email"] = attrs.get("email") or None
            attrs["phone"] = attrs.get("phone") or None

            email = attrs["email"]
            phone = attrs["phone"]
            role  = attrs.get("role")

            valid_roles = [c[0] for c in self.ROLE_CHOICES]
            if role not in valid_roles:
                raise serializers.ValidationError(
                    {"role": _("Invalid role. Must be 'vendor' or 'client'.")}
                )

            if email and phone:
                raise serializers.ValidationError({
                    "non_field_errors": [_(
                        "Please provide either an email address or a "
                        "phone number, not both."
                    )]
                })

            if not email and not phone:
                raise serializers.ValidationError({
                    "non_field_errors": [_(
                        "Please provide either an email address or a "
                        "phone number; one is required."
                    )]
                })

            # Normalise email domain to lowercase
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email:
                email = _BUM.normalize_email(email)
                attrs["email"] = email

            # Soft-deleted pool check FIRST (prevents unique-constraint 500)
            from apps.authentication.exceptions import SoftDeletedUserExistsError

            if email:
                if UnifiedUser.objects.all_with_deleted().filter(
                    email__iexact=email, is_deleted=True
                ).exists():
                    logger.warning(
                        "⛔ Registration blocked: soft-deleted account email '%s'", email
                    )
                    raise SoftDeletedUserExistsError()

            if phone:
                if UnifiedUser.objects.all_with_deleted().filter(
                    phone=phone, is_deleted=True
                ).exists():
                    logger.warning(
                        "⛔ Registration blocked: soft-deleted account phone '%s'", phone
                    )
                    raise SoftDeletedUserExistsError()

            # Active uniqueness check
            if email and UnifiedUser.objects.filter(email__iexact=email).exists():
                raise serializers.ValidationError(
                    {"email": _("A user with this email address already exists.")}
                )
            if phone and UnifiedUser.objects.filter(phone=phone).exists():
                raise serializers.ValidationError(
                    {"phone": _("A user with this phone number already exists.")}
                )

            logger.info("Registration validation successful.")
            return attrs

        except (serializers.ValidationError, SoftDeletedUserExistsError):
            raise
        except Exception as exc:
            logger.error("Unexpected error in registration validation: %s", exc)
            raise serializers.ValidationError(
                {"non_field_errors": _("An error occurred during validation.")}
            )

    def create(self, validated_data):
        try:
            from apps.authentication.services.registration_service import (
                RegistrationService,
            )
            validated_data.pop("password2", None)
            validated_data.pop("password_confirm", None)

            result = RegistrationService.register_sync(**validated_data)

            from apps.authentication.models import UnifiedUser as _UU
            user = _UU.objects.get(id=result["user_id"])

            logger.info(
                "✅ User created via serializer: %s (ID: %s, Role: %s)",
                user.email or user.phone, user.id, user.role,
            )
            return user
        except Exception as exc:
            logger.error("❌ Error creating user via serializer: %s", exc, exc_info=True)
            raise serializers.ValidationError(
                {"error": f"An error occurred during user creation: {exc}"}
            )


class AsyncUserRegistrationSerializer(UserRegistrationSerializer):
    """Asynchronous version of UserRegistrationSerializer."""

    async def acreate(self, validated_data):
        return self.create(validated_data)


# ─── Logout / Token Refresh ───────────────────────────────────────────────────

class LogoutSerializer(serializers.Serializer):
    """Accepts the refresh token to blacklist on logout."""
    refresh = serializers.CharField(
        required=True,
        help_text="Refresh token to blacklist on logout.",
    )

    class Meta:
        ref_name = "AuthLogout"


class TokenRefreshSerializer(serializers.Serializer):
    """
    Wraps SimpleJWT token refresh for drf-yasg Swagger schema generation.
    """
    refresh = serializers.CharField(
        required=True,
        help_text="A valid refresh token previously issued by the login endpoint.",
    )

    class Meta:
        ref_name = "AuthTokenRefresh"


# ─── Google OAuth ─────────────────────────────────────────────────────────────

class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google ID Token authentication."""
    id_token = serializers.CharField(required=True, help_text="Google ID Token")

    ROLE_CHOICES = getattr(
        UnifiedUser, "ROLE_CHOICES", [("vendor", "Vendor"), ("client", "Client")]
    )
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
        default="client",
        help_text="User's role",
    )

    class Meta:
        ref_name = "AuthGoogleAuth"

    def validate(self, attrs):
        try:
            if not attrs.get("id_token"):
                raise serializers.ValidationError(
                    {"id_token": _("Google ID Token is required.")}
                )
            valid_roles = [c[0] for c in self.ROLE_CHOICES]
            if attrs.get("role") not in valid_roles:
                raise serializers.ValidationError({"role": _("Invalid role.")})
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.error("Google auth validation error: %s", exc)
            raise serializers.ValidationError(
                {"non_field_errors": _("An error occurred during Google Auth validation.")}
            )
