# apps/authentication/serializers/auth.py
"""
Auth Serializers — Login, Registration, Logout, Token Refresh, Google OAuth.

Part of the serializers/ folder split (Bug 9).
Previously in the monolithic serializers.py.
"""

import logging

from apps.authentication.models import UnifiedUser
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
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
            # Normalise email domain to lowercase only for email (phone remains unchanged)
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email_or_phone and "@" in email_or_phone:
                email_or_phone = _BUM.normalize_email(email_or_phone)
                data["email_or_phone"] = email_or_phone

            # ── Step 1: Alive-only lookup (✅ 1 DB HIT using Q) ─────────────
            user = UnifiedUser.objects.filter(
                Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)
            ).first()

            if user is None:
                # ── Step 2: Soft-deleted pool check (✅ 1 DB HIT using Q) ─
                if UnifiedUser.objects.all_with_deleted().filter(
                    (Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)),
                    is_deleted=True
                ).exists():
                    logger.warning(
                        "⛔ Login rejected: soft-deleted account '%s'", email_or_phone
                    )
                    raise SoftDeletedUserError()

                # User not found at all
                logger.warning("⛔ Login failed: user not found '%s'", email_or_phone)
                raise InvalidCredentialsError()

            # ── Step 3: Password check ────────────────────────────────────
            if not user.check_password(password):
                logger.warning(
                    "⛔ Login failed: wrong password for '%s'", email_or_phone
                )
                raise InvalidCredentialsError()

            # ── Step 4a: Check if the user has verified their OTP (FIRST — before is_active) ──────
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

    first_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="User's first name",
    )
    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="User's last name",
    )

    ROLE_CHOICES = [("vendor", "Vendor"), ("client", "Client")]
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
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
                logger.warning("Registration failed: Passwords do not match.")
                raise serializers.ValidationError(
                    {"password": _("Passwords do not match.")}
                )

            # Normalise empty strings → None
            attrs["email"] = attrs.get("email") or None
            attrs["phone"] = attrs.get("phone") or None
            attrs["first_name"] = attrs.get("first_name") or None
            attrs["last_name"] = attrs.get("last_name") or None

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

            # Normalise email domain to lowercase (only for email)
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email:
                email = _BUM.normalize_email(email)
                attrs["email"] = email

            # Soft-deleted pool check FIRST (prevents unique-constraint 500)
            # ✅ OPTIMIZED: Single database query using Q object (one-liner)
            if (email or phone) and UnifiedUser.objects.all_with_deleted().filter(
                (Q(email__iexact=email) if email else Q(phone=phone)),
                is_deleted=True
            ).exists():
                logger.warning(
                    "⛔ Registration blocked: soft-deleted account '%s' or '%s'", email, phone
                )
                raise SoftDeletedUserExistsError()

            # Active uniqueness check (✅ OPTIMIZED: Single query using Q one-liner)
            if (email or phone) and UnifiedUser.objects.filter(
                (Q(email__iexact=email) if email else Q(phone=phone))
            ).exists():
                raise serializers.ValidationError({
                    "email" if email else "phone": [_(
                        "A user with this email address already exists."
                        if email else "A user with this phone number already exists."
                    )]
                })

            logger.info("Registration validation successful.")
            return attrs

        except (serializers.ValidationError, SoftDeletedUserExistsError):
            raise
        except Exception as exc:
            logger.error("Unexpected error in registration validation: %s", exc, exc_info=True)
            raise serializers.ValidationError(
                {"non_field_errors": f"An error occurred during validation: {str(exc)}"}
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
    """
    Serializer for Google ID Token authentication.

    Flow:
        Login (existing user): { id_token }  — role is optional, ignored
        Register (new user):   { id_token, role: 'vendor'|'client' }
    """
    id_token = serializers.CharField(
        required=True,
        help_text="Google ID Token (JWT) returned by @react-oauth/google on the frontend.",
    )

    ROLE_CHOICES = getattr(
        UnifiedUser, "ROLE_CHOICES", [("vendor", "Vendor"), ("client", "Client")]
    )
    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
        default="client",
        required=False,       # ← Optional: for login, role is derived from DB record
        allow_blank=True,     # ← Permits "" from frontend during login
        help_text="User's role — required for new registrations, ignored for existing users.",
    )

    class Meta:
        ref_name = "AuthGoogleAuth"

    def validate(self, attrs):
        try:
            if not attrs.get("id_token"):
                raise serializers.ValidationError(
                    {"id_token": _("Google ID Token is required.")}
                )
            # Normalise role: strip blanks, default to 'client'
            role = (attrs.get("role") or "client").strip().lower()
            valid_roles = [c[0] for c in self.ROLE_CHOICES]
            if role not in valid_roles:
                role = "client"
            attrs["role"] = role
            return attrs
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.error("Google auth validation error: %s", exc)
            raise serializers.ValidationError(
                {"non_field_errors": _("An error occurred during Google Auth validation.")}
            )

