# apps/authentication/serializers/otp.py
"""
OTP Serializers — ResendOTPRequestSerializer.

Part of the serializers/ folder split (Bug 9).
Previously in the monolithic serializers.py.
"""

from apps.authentication.exceptions import SoftDeletedUserExistsError
import logging

from apps.authentication.models import UnifiedUser
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

logger = logging.getLogger(__name__)


class ResendOTPRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting OTP resend by email or phone.

    CRITICAL FIX: Uses ``all_with_deleted()`` manager so that users who
    just registered (is_active=False, is_verified=False) are found.
    A newly-registered unverified user IS alive — they just haven't
    been activated yet.
    """
    email_or_phone = serializers.CharField(
        write_only=True,
        required=True,
        help_text="User's email or phone for resend OTP",
    )

    class Meta:
        ref_name = "AuthResendOTPRequest"

    def validate(self, data):
        try:
            email_or_phone = data.get("email_or_phone")
            
            
            # Normalise email domain to lowercase
            from django.contrib.auth.base_user import BaseUserManager as _BUM
            if email_or_phone:
                email_or_phone = _BUM.normalize_email(email_or_phone)
                data["email_or_phone"] = email_or_phone


            # Soft-deleted pool check FIRST (prevents unique-constraint 500)
            # ✅ OPTIMIZED: Single database query using Q object
            if email_or_phone:
                if UnifiedUser.objects.all_with_deleted().filter(
                    (Q(email__iexact=email_or_phone) | Q(phone=email_or_phone)) & Q(is_deleted=True)
                ).exists():
                    logger.warning(
                        "⛔ Resend OTP blocked: soft-deleted account '%s'", email_or_phone
                    )
                    raise SoftDeletedUserExistsError()
            
            # ✅ OPTIMIZED: Single database query using Q object for both email and phone
            user = UnifiedUser.objects.all_with_deleted().filter(
                Q(email=email_or_phone) if "@" in email_or_phone else Q(phone=email_or_phone)
            ).first()

            if not user:
                logger.warning(
                    "ResendOTP validation failed: no user for '%s'", email_or_phone
                )
                raise serializers.ValidationError({
                    "email_or_phone": [_(
                        "No account found with this email or phone. "
                        "Please check your input or register a new account."
                    )]
                })

            data["user"] = user
            logger.info("ResendOTP validation successful for %s", email_or_phone)
            return data

        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "ResendOTP failed for %s: %s", data.get("email_or_phone"), exc
            )
            raise serializers.ValidationError({
                "email_or_phone": [_("User with this email or phone not found.")]
            })
