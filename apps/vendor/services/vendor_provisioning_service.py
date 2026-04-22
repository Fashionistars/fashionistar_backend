# apps/vendor/services/vendor_provisioning_service.py
"""
VendorProvisioningService — explicit vendor setup provisioning.

Unlike clients, vendors are NOT auto-provisioned on registration. This
service is called only from the vendor setup flow to create the first
domain records needed for dashboard access.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VendorProvisioningService:
    """
    Idempotent provisioner for the vendor domain.

    Usage:
        VendorProvisioningService.provision(user)
    """

    @staticmethod
    def provision(user, *, data: dict[str, Any]) -> "VendorProfile":  # noqa: F821
        """
        Create or update the initial vendor setup records for ``user``.

        Args:
            user: UnifiedUser instance with role='vendor'.
            data: Validated vendor setup payload.

        Returns:
            VendorProfile instance (new or existing).
        """
        from django.db import transaction
        from apps.vendor.models import VendorProfile, VendorSetupState

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

        with transaction.atomic():
            profile, profile_created = VendorProfile.objects.get_or_create(user=user)

            update_fields = ["updated_at"]
            for field, value in data.items():
                if field in allowed_fields:
                    setattr(profile, field, value)
                    update_fields.append(field)
            profile.save(update_fields=update_fields)

            setup_state, setup_created = VendorSetupState.objects.get_or_create(
                vendor=profile
            )
            if profile.store_name and profile.description:
                setup_state.mark_profile_complete()

            if profile_created:
                logger.info(
                    "VendorProvisioningService: created VendorProfile for user %s",
                    user.pk,
                )
            if setup_created:
                logger.info(
                    "VendorProvisioningService: created VendorSetupState for vendor %s",
                    profile.pk,
                )

        return profile
