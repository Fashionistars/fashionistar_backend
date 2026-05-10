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
MIN_COLLECTIONS = 1
MAX_COLLECTIONS = 15

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

        # Extract non-field data before iterating.
        collection_ids = list(dict.fromkeys(data.get("collection_ids", [])))
        if not (MIN_COLLECTIONS <= len(collection_ids) <= MAX_COLLECTIONS):
            raise ValueError("Vendor setup requires between 1 and 15 collections.")

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
            from apps.catalog.models import Collections as CollectionModel

            qs = CollectionModel.objects.filter(pk__in=collection_ids)
            if qs.count() != len(collection_ids):
                raise ValueError("One or more selected collections do not exist.")
            profile.collections.set(qs)

            # ── Setup State ────────────────────────────────────────
            setup_state, setup_created = VendorSetupState.objects.get_or_create(
                vendor=profile
            )

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

        # Audit trail — vendor onboarding (compliance-grade)
        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory, SeverityLevel
            AuditService.log(
                event_type=EventType.VENDOR_PROVISIONED if profile_created else EventType.VENDOR_PROFILE_UPDATED,
                event_category=EventCategory.VENDOR,
                severity=SeverityLevel.INFO,
                action=f"Vendor {'provisioned' if profile_created else 'profile updated'}: user={user.pk} store={data.get('store_name', '')}",
                actor=user,
                actor_role="vendor",
                resource_type="VendorProfile",
                resource_id=str(profile.pk),
                new_values={
                    "store_name": data.get("store_name"),
                    "city": data.get("city"),
                    "state": data.get("state"),
                    "country": data.get("country"),
                    "collections_count": len(collection_ids),
                },
                is_compliance=True,
                retention_days=2555,
            )
        except Exception:
            pass
        return profile
