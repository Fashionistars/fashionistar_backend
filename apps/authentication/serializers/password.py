# apps/authentication/serializers/password.py
"""
Password Serializers — Reset Request, Reset Confirm (Email + Phone), Change Password.

Part of the serializers/ folder split (Bug 9).
Previously in the monolithic serializers.py.
"""

import logging

from apps.authentication.exceptions import SoftDeletedUserError
from apps.authentication.models import UnifiedUser
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

logger = logging.getLogger(__name__)


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting password reset.

    Uses all_with_deleted() so soft-deleted users can still trigger a reset.
    Anti-enumeration: always returns 200 regardless of whether user exists.
    """
    email_or_phone = serializers.CharField(
        write_only=True,
        required=True,
        help_text="User's email or phone for password reset",
    )

    class Meta:
        ref_name = "AuthPasswordResetRequest"

    def validate(self, data):
        try:
            email_or_phone = data.get("email_or_phone")

            # Normalise email domain to lowercase only for email (phone remains unchanged)
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email_or_phone and "@" in email_or_phone:
                email_or_phone = _BUM.normalize_email(email_or_phone)
                data["email_or_phone"] = email_or_phone

            # Soft-deleted pool check FIRST (prevents unique-constraint 500)
            if UnifiedUser.objects.all_with_deleted().filter(
                (Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)),
                is_deleted=True
            ).exists():
                logger.warning(
                    "⛔ Password Reset Request Rejected: soft-deleted account '%s'", email_or_phone
                )
                raise SoftDeletedUserError()



            # ✅ OPTIMIZED: Single database query using Q object
            user =  UnifiedUser.objects.all_with_deleted().filter(
                Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)
            ).first()  # Anti-enumeration: ignore None

            data["user"] = user
            logger.info("Password reset request validation successful for %s", email_or_phone)
            return data
        except SoftDeletedUserError:
            raise
        except Exception as exc:
            logger.warning(
                "Password reset request validation error for %s: %s",
                data.get("email_or_phone"), exc,
                ~"Returning success response to prevent account enumeration."
            )            
            return data  # Always pass validation — prevents enumeration attacks by giving same response for existing vs non-existing users

class PasswordResetConfirmEmailSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset via email magic link.

    Validates the new password and confirmation match.
    The uidb64 + token URL params are merged in by the view.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        help_text="New password",
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Confirm new password",
    )

    class Meta:
        ref_name = "AuthPasswordResetConfirmEmail"

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": _("Passwords do not match.")}
            )
        return attrs


class PasswordResetConfirmPhoneSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset via phone OTP.

    OTP-ONLY design (mirrors VerifyOTPView pattern exactly):
      - Client sends ONLY: otp + password + password2.
      - phone is NOT required in the body — the service discovers the user
        via OTPService.verify_by_otp_sync(otp, purpose='password_reset'),
        which uses an O(1) SHA-256 hash index lookup in Redis:
            otp_hash:{sha256(otp)}  →  otp:{user_id}:password_reset:{snippet}
      - This prevents account enumeration: an attacker cannot test whether
        a phone number has an account by observing different error responses.

    Redis key schema (written during reset-request):
      Primary  : otp:{user_id}:password_reset:{snippet}
                 Value = "{encrypted_otp}|{sha256_hex}"
      Secondary: otp_hash:{sha256_hex}  →  primary_key  (TTL = 300 s)
    """
    otp = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=6,
        help_text="6-digit OTP received via SMS",
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        help_text="New password",
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Confirm new password",
    )

    class Meta:
        ref_name = "AuthPasswordResetConfirmPhone"

    def validate(self, attrs):
        try:
            from django.conf import settings as _s
            _base = getattr(_s, "FRONTEND_URL", "http://localhost:3000").rstrip("/")

            if attrs["password"] != attrs["password2"]:
                raise serializers.ValidationError(
                    {"password": _("Passwords do not match.")}
                )

            otp = attrs.get("otp", "")
            if not otp or len(otp) != 6 or not otp.isdigit():
                raise serializers.ValidationError({
                    "otp": _(
                        "OTP must be exactly 6 numeric digits. "
                        "Didn't receive it? Request a new one."
                    ),
                    "resend_otp_url":    f"{_base}/resend-otp",
                    "reset_request_url": "/api/v1/password/reset-request/",
                })

            return attrs
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.error("Unexpected error in PasswordResetConfirmPhoneSerializer: %s", exc)
            raise serializers.ValidationError(
                {"non_field_errors": _("Validation failed.")}
            )


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for authenticated password change from the dashboard.
    Validates old password + new password match.
    """
    old_password     = serializers.CharField(write_only=True, required=True,
                                              help_text="Current password")
    new_password     = serializers.CharField(write_only=True, required=True,
                                              validators=[validate_password],
                                              help_text="New password")
    confirm_password = serializers.CharField(write_only=True, required=True,
                                              help_text="Confirm new password")

    def validate(self, attrs):
        try:
            if attrs["new_password"] != attrs["confirm_password"]:
                raise serializers.ValidationError(
                    {"new_password": _("New passwords do not match.")}
                )

            request = self.context.get("request")
            if request and request.user:
                if not request.user.check_password(attrs["old_password"]):
                    raise serializers.ValidationError(
                        {"old_password": _("Incorrect old password.")}
                    )

            return attrs
        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.error("Password change validation error: %s", exc)
            raise serializers.ValidationError(
                {"non_field_errors": _("An error occurred during password change.")}
            )
