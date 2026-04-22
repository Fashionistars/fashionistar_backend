# apps/vendor/services/vendor_service.py
"""
VendorService — All business logic for vendor profile CRUD.

Design principles:
  - All mutations go through here, never from views directly.
  - EventBus events emitted AFTER transaction.on_commit().
  - Uses typed dict helpers for clear param contracts.
"""
import logging
from typing import Any

from django.db import transaction

from apps.common.events import event_bus

logger = logging.getLogger(__name__)


class VendorService:
    """
    Service layer for vendor profile operations.
    """

    # ── Retrieve ───────────────────────────────────────────────────

    @classmethod
    def get_profile(cls, user) -> "VendorProfile":  # noqa: F821
        """Return the existing VendorProfile for ``user``."""
        from apps.vendor.models import VendorProfile
        return VendorProfile.objects.get(user=user)

    # ── Update Profile ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def update_profile(cls, user, data: dict[str, Any]) -> "VendorProfile":  # noqa: F821
        """
        Partial update of VendorProfile fields.

        Emits: vendor.profile.updated (after commit)
        """
        from apps.vendor.models import VendorProfile, VendorSetupState

        profile = VendorProfile.objects.select_for_update().get(user=user)

        allowed_fields = {
            "store_name",
            "tagline",
            "description",
            "logo_url",
            "cover_url",
            "city",
            "state",
            "country",
            "instagram_url",
            "tiktok_url",
            "twitter_url",
            "website_url",
        }

        update_fields = ["updated_at"]
        for field, value in data.items():
            if field in allowed_fields:
                setattr(profile, field, value)
                update_fields.append(field)

        profile.save(update_fields=update_fields)

        # Check if profile setup step can be marked complete
        has_basics = all([
            profile.store_name,
            profile.description,
        ])
        if has_basics:
            try:
                setup_state = profile.setup_state
                setup_state.mark_profile_complete()
            except Exception:
                pass  # VendorSetupState may not exist yet — provisioner handles this

        event_bus.emit_on_commit(
            "vendor.profile.updated",
            user_id=str(user.pk),
            profile_id=str(profile.pk),
            fields=list(update_fields),
        )

        logger.info(
            "VendorService.update_profile: updated profile %s for user %s",
            profile.pk, user.pk,
        )
        return profile

    # ── Payout Profile ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def save_payout_details(cls, user, data: dict[str, Any]) -> "VendorPayoutProfile":  # noqa: F821
        """
        Create or update the vendor's payout (bank account) profile.

        Encrypts account_number before storage.
        """
        from apps.vendor.models import VendorProfile, VendorPayoutProfile

        profile = VendorProfile.objects.select_for_update().get(user=user)

        # Encrypt account number
        account_number = data.pop("account_number", "")
        account_last4  = account_number[-4:] if len(account_number) >= 4 else account_number

        try:
            from django.conf import settings
            from cryptography.fernet import Fernet
            fernet_key = settings.FERNET_ENCRYPTION_KEY.encode()
            f = Fernet(fernet_key)
            account_number_enc = f.encrypt(account_number.encode())
        except Exception:
            logger.warning(
                "VendorService.save_payout_details: encryption unavailable — "
                "storing blank encrypted value for vendor %s", profile.pk
            )
            account_number_enc = b""

        payout, _ = VendorPayoutProfile.objects.update_or_create(
            vendor=profile,
            defaults={
                "bank_name": data.get("bank_name", ""),
                "bank_code": data.get("bank_code", ""),
                "account_name": data.get("account_name", ""),
                "account_number_enc": account_number_enc,
                "account_last4": account_last4,
                "paystack_recipient_code": data.get("paystack_recipient_code", ""),
            },
        )

        # Mark bank_details setup step complete
        try:
            profile.setup_state.mark_bank_details()
        except Exception:
            pass

        logger.info(
            "VendorService.save_payout_details: saved payout for vendor %s", profile.pk
        )
        return payout
