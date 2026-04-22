# apps/vendor/services/vendor_provisioning_service.py
"""
VendorProvisioningService — Auto-provision VendorProfile + VendorSetupState.

Called by EventBus `user.registered` handler (role=vendor).
Idempotent — safe to call multiple times.
"""
import logging

logger = logging.getLogger(__name__)


class VendorProvisioningService:
    """
    Idempotent provisioner for the vendor domain.

    Usage:
        VendorProvisioningService.provision(user)
    """

    @staticmethod
    def provision(user) -> "VendorProfile":  # noqa: F821
        """
        Create blank VendorProfile + VendorSetupState for `user`.

        Args:
            user: UnifiedUser instance with role='vendor'.

        Returns:
            VendorProfile instance (new or existing).
        """
        from django.db import transaction
        from apps.vendor.models import VendorProfile, VendorSetupState

        with transaction.atomic():
            profile, profile_created = VendorProfile.objects.get_or_create(user=user)
            _, setup_created = VendorSetupState.objects.get_or_create(vendor=profile)

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
