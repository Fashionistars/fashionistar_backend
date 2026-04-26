# apps/vendor/services/vendor_provisioning_service.py
"""
VendorProvisioningService — explicit vendor setup provisioning.

Unlike clients, vendors are NOT auto-provisioned on registration. This
service is called only from the vendor setup flow (POST /api/v1/vendor/setup/)
to create the initial domain records needed for full dashboard access.

Idempotent: calling provision() on an already-provisioned vendor simply
updates the profile fields and returns the existing profile.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Fields the provisioner is allowed to write on first-time setup ──
PROVISION_ALLOWED_FIELDS = {
    "store_name",
    "tagline",
    "description",
    "logo_url",
    "cover_url",
    "city",
    "state",
    "country",
    "whatsapp",
    "opening_time",
    "closing_time",
    "business_hours",
    "instagram_url",
    "tiktok_url",
    "twitter_url",
    "website_url",
}


class VendorProvisioningService:
    """
    Idempotent provisioner for the vendor domain.

    Usage:
        profile = VendorProvisioningService.provision(user, data=validated_data)
    """

    @staticmethod
    def provision(user, *, data: dict[str, Any]) -> "VendorProfile":  # noqa: F821
        """
        Create or update the initial vendor setup records for ``user``.

        Args:
            user: UnifiedUser instance with role='vendor'.
            data: Validated vendor setup payload (from VendorSetupSerializer).

        Returns:
            VendorProfile instance (new or existing).
        """
        from django.db import transaction
        from apps.vendor.models import VendorProfile, VendorSetupState

        # Extract non-field data before iterating
        collection_ids = data.get("collection_ids", [])

        with transaction.atomic():
            profile, profile_created = VendorProfile.objects.get_or_create(user=user)

            # ── Scalar fields ──────────────────────────────────────
            update_fields = ["updated_at"]
            for field, value in data.items():
                if field in PROVISION_ALLOWED_FIELDS:
                    setattr(profile, field, value)
                    update_fields.append(field)
            profile.save(update_fields=update_fields)

            # ── Collections M2M ────────────────────────────────────
            if collection_ids:
                from apps.catalog.models import Collections as CollectionModel
                qs = CollectionModel.objects.filter(pk__in=collection_ids)
                profile.collections.set(qs)

            # ── Setup State ────────────────────────────────────────
            setup_state, setup_created = VendorSetupState.objects.get_or_create(vendor=profile)

            # Advance profile_complete step if basics are present
            if profile.store_name and profile.description:
                setup_state.mark_profile_complete()

            if profile_created:
                logger.info(
                    "VendorProvisioningService.provision: created VendorProfile for user=%s",
                    user.pk,
                )
            if setup_created:
                logger.info(
                    "VendorProvisioningService.provision: created VendorSetupState for vendor=%s",
                    profile.pk,
                )

        return profile
