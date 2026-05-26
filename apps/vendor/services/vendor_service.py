# apps/vendor/services/vendor_service.py
"""
VendorService — All business logic for vendor profile CRUD.

Design principles:
  ─ All mutations go through here, never from views directly.
  ─ EventBus events emitted AFTER transaction.on_commit().
  ─ No raw SQL, no sync_to_async().
  ─ Fernet encryption for bank account number.
  ─ Collections M2M is managed via set() on the profile.
  ─ All field updates use explicit update_fields= to prevent race conditions.
"""

import logging
from typing import Any

from django.db import transaction

from apps.common.events import event_bus

logger = logging.getLogger(__name__)
MIN_COLLECTIONS = 1
MAX_COLLECTIONS = 15


def _minimum_collection_count() -> int:
    from apps.catalog.models import Collections as CollectionModel

    return MIN_COLLECTIONS if CollectionModel.objects.exists() else 0

# ── Fields the vendor is allowed to update on their own profile ──
VENDOR_PROFILE_ALLOWED_FIELDS = {
    "store_name",
    "tagline",
    "description",
    "logo_url",
    "cover_url",
    "city",
    "state",
    "country",
    "opening_time",
    "closing_time",
    "business_hours",
    "instagram_url",
    "tiktok_url",
    "twitter_url",
    "website_url",
    "whatsapp",
}


class VendorService:
    """
    Service layer for vendor profile operations.
    Sync methods only — async operations live in selectors/ (reads)
    and can be added here as async class methods if needed in the future.
    """

    # ── Retrieve ───────────────────────────────────────────────────

    @classmethod
    def get_profile(cls, user) -> "VendorProfile":  # noqa: F821
        """Return the existing VendorProfile for ``user``. Raises DoesNotExist if absent."""
        from apps.vendor.models import VendorProfile

        return (
            VendorProfile.objects.select_related(
                "user", "vendor_setup_state", "vendor_payout_profile"
            )
            .prefetch_related("collections")
            .get(user=user)
        )

    # ── Update Profile ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def update_profile(
        cls, user, data: dict[str, Any], request=None
    ) -> "VendorProfile":  # noqa: F821
        """Partial update of VendorProfile fields.

        Handles both scalar fields and the M2M `collections` field.
        Emits: vendor.profile.updated (after commit)

        Args:
            user: The user owning the profile.
            data: Dict of fields to update.
            request: Optional Django HttpRequest for forensic audit logging.

        Returns:
            The updated VendorProfile instance.
        """
        from apps.vendor.models import VendorProfile

        profile = VendorProfile.objects.select_for_update().get(user=user)

        # ── Scalar field updates ───────────────────────────────────
        update_fields = ["updated_at"]
        audit_changes = {}
        for field, value in data.items():
            if field in VENDOR_PROFILE_ALLOWED_FIELDS:
                old_val = getattr(profile, field, None)
                if old_val != value:
                    setattr(profile, field, value)
                    update_fields.append(field)
                    audit_changes[field] = value

        profile.save(update_fields=update_fields)

        # ── Collections M2M (e.g. ["ready-to-wear", "accessories"]) ──
        # The caller passes collection PKs or UUIDs as a list.
        if "collection_ids" in data:
            from apps.catalog.models import Collections as CollectionModel

            ids = list(dict.fromkeys(data["collection_ids"]))
            min_collections = _minimum_collection_count()
            if not (min_collections <= len(ids) <= MAX_COLLECTIONS):
                if min_collections == 0:
                    raise ValueError("Vendor profile can keep zero collections only while the catalog has none.")
                raise ValueError("Vendor profile requires between 1 and 15 collections.")
            if ids:
                qs = CollectionModel.objects.filter(pk__in=ids)
                if qs.count() != len(ids):
                    raise ValueError("One or more selected collections do not exist.")
                profile.collections.set(qs)
            else:
                profile.collections.clear()
            audit_changes["collections"] = ids

        # ── Auto-advance onboarding step ───────────────────────────
        has_basics = bool(profile.store_name and profile.description)
        if has_basics:
            try:
                profile.vendor_setup_state.mark_profile_complete()
            except Exception:
                pass  # VendorSetupState may not exist yet — provisioner handles creation

        # ── Forensic Audit Trail (Atomic Dispatch) ────────────────
        def _dispatch_audit():
            try:
                from apps.audit_logs.services.vendor import vendor_audit
                vendor_audit.log_vendor_profile_updated(
                    actor=user,
                    vendor_profile=profile,
                    new_values=audit_changes,
                    request=request,
                )
            except Exception as audit_exc:
                logger.error("VendorService.update_profile: Audit failed: %s", audit_exc)

        transaction.on_commit(_dispatch_audit)

        event_bus.emit_on_commit(
            "vendor.profile.updated",
            user_id=str(user.pk),
            profile_id=str(profile.pk),
            fields=list(update_fields),
        )

        logger.info(
            "VendorService.update_profile: updated profile=%s for user=%s",
            profile.pk,
            user.pk,
        )
        return profile

    # ── Payout Profile ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def save_payout_details(
        cls, user, data: dict[str, Any], request=None
    ) -> "VendorPayoutProfile":  # noqa: F821
        """Create or update the vendor's payout (bank account) profile.

        Encrypts account_number before storage using Fernet (FERNET_ENCRYPTION_KEY).
        Marks bank_details onboarding step complete.
        Emits: vendor.payout.updated (after commit)

        Args:
            user: The vendor user.
            data: Dict containing bank_name, bank_code, account_name, account_number.
            request: Optional Django HttpRequest for forensic audit logging.

        Returns:
            The created or updated VendorPayoutProfile instance.
        """
        from apps.vendor.models import VendorProfile, VendorPayoutProfile

        profile = VendorProfile.objects.select_for_update().get(user=user)

        # Encrypt account number — copy dict so we don't mutate the caller's object
        data = dict(data)
        account_number = data.pop("account_number", "")
        account_last4 = (
            account_number[-4:] if len(account_number) >= 4 else account_number
        )

        account_number_enc: bytes = b""
        try:
            from django.conf import settings
            from cryptography.fernet import Fernet

            fernet_key = settings.FERNET_ENCRYPTION_KEY.encode()
            f = Fernet(fernet_key)
            account_number_enc = f.encrypt(account_number.encode())
        except Exception as enc_exc:
            logger.warning(
                "VendorService.save_payout_details: encryption failed for vendor=%s: %s",
                profile.pk,
                enc_exc,
            )

        payout, created = VendorPayoutProfile.objects.update_or_create(
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

        # Mark bank_details onboarding step complete
        try:
            profile.vendor_setup_state.mark_bank_details()
        except Exception:
            pass

        # ── Forensic Audit Trail (Atomic Dispatch) ────────────────
        def _dispatch_audit():
            try:
                from apps.audit_logs.services.vendor import vendor_audit
                vendor_audit.log_vendor_payout_updated(
                    actor=user,
                    vendor_profile=profile,
                    created=created,
                    request=request,
                )
            except Exception as audit_exc:
                logger.error("VendorService.save_payout_details: Audit failed: %s", audit_exc)

        transaction.on_commit(_dispatch_audit)

        event_bus.emit_on_commit(
            "vendor.payout.updated",
            user_id=str(user.pk),
            vendor_id=str(profile.pk),
            created=created,
        )

        logger.info(
            "VendorService.save_payout_details: saved payout for vendor=%s (created=%s)",
            profile.pk,
            created,
        )
        return payout

    # ── Transaction PIN ────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def set_transaction_pin(cls, user, raw_pin: str, request=None) -> None:
        """Hash and store a 4-digit payout confirmation PIN.

        Validates PIN is exactly 4 digits.

        Args:
            user: The vendor user.
            raw_pin: The 4-digit numeric string.
            request: Optional Django HttpRequest for forensic audit logging.

        Raises:
            ValueError: If PIN is not exactly 4 digits.
        """
        from apps.vendor.models import VendorProfile

        if not raw_pin.isdigit() or len(raw_pin) != 4:
            raise ValueError("Transaction PIN must be exactly 4 digits.")

        profile = VendorProfile.objects.select_for_update().get(user=user)
        profile.set_transaction_password(raw_pin)

        # ── Forensic Audit Trail (Atomic Dispatch) ────────────────
        def _dispatch_audit():
            try:
                from apps.audit_logs.services.vendor import vendor_audit
                vendor_audit.log_vendor_pin_updated(
                    actor=user,
                    vendor_profile=profile,
                    request=request,
                )
            except Exception as audit_exc:
                logger.error("VendorService.set_transaction_pin: Audit failed: %s", audit_exc)

        transaction.on_commit(_dispatch_audit)

        logger.info(
            "VendorService.set_transaction_pin: PIN updated for vendor=%s", profile.pk
        )

    @classmethod
    def verify_transaction_pin(cls, user, raw_pin: str) -> bool:
        """Verify the provided PIN against the stored bcrypt hash."""
        from apps.vendor.models import VendorProfile

        profile = VendorProfile.objects.get(user=user)
        return profile.check_transaction_password(raw_pin)

    # ── Mark First Product ─────────────────────────────────────────

    @classmethod
    def on_first_product_listed(cls, vendor_profile) -> None:
        """
        Called by product service when vendor lists their first product.
        Marks the first_product onboarding milestone and triggers onboarding_done check.
        """
        try:
            vendor_profile.vendor_setup_state.mark_first_product()
            logger.info(
                "VendorService.on_first_product_listed: first_product marked for vendor=%s",
                vendor_profile.pk,
            )
        except Exception as exc:
            logger.error(
                "VendorService.on_first_product_listed: error for vendor=%s: %s",
                vendor_profile.pk,
                exc,
            )
