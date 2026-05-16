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


def _collection_requirements() -> tuple[int, int, bool]:
    from apps.catalog.models import Collections as CollectionModel

    has_any_collections = CollectionModel.objects.exists()
    return (MIN_COLLECTIONS if has_any_collections else 0, MAX_COLLECTIONS, has_any_collections)

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
    def provision(user, *, data: dict[str, Any], request=None) -> "VendorProfile":  # noqa: F821
        """Create or update the initial vendor setup records for ``user``.

        Args:
            user: UnifiedUser instance with role='vendor'.
            data: Validated vendor setup payload (from VendorSetupSerializer).
            request: Optional Django HttpRequest for forensic audit logging.

        Returns:
            VendorProfile instance (new or existing).
        """
        from django.db import transaction
        from apps.vendor.models import VendorProfile, VendorSetupState

        # Extract non-field data before iterating.
        collection_ids = list(dict.fromkeys(data.get("collection_ids", [])))
        min_collections, max_collections, has_any_collections = _collection_requirements()
        if not (min_collections <= len(collection_ids) <= max_collections):
            if has_any_collections:
                raise ValueError("Vendor setup requires between 1 and 15 collections.")
            raise ValueError("Vendor setup currently accepts zero collections because none exist in the catalog yet.")

        with transaction.atomic():
            # Use select_for_update for consistency during the setup transaction
            profile, profile_created = VendorProfile.objects.select_for_update().get_or_create(user=user)

            # ── Scalar fields ──────────────────────────────────────
            update_fields = ["updated_at"]
            for field, value in data.items():
                if field in PROVISION_ALLOWED_FIELDS:
                    setattr(profile, field, value)
                    update_fields.append(field)
            profile.save(update_fields=update_fields)

            # ── Collections M2M ────────────────────────────────────
            from apps.catalog.models import Collections as CollectionModel

            if collection_ids:
                qs = CollectionModel.objects.filter(pk__in=collection_ids)
                if qs.count() != len(collection_ids):
                    raise ValueError("One or more selected collections do not exist.")
                profile.collections.set(qs)
            else:
                profile.collections.clear()

            # ── Setup State ────────────────────────────────────────
            setup_state, setup_created = VendorSetupState.objects.get_or_create(
                vendor=profile
            )

            # Advance profile_complete step if basics are present
            if profile.store_name and profile.description:
                setup_state.mark_profile_complete()

            # ── Forensic Audit Trail (Atomic Dispatch) ────────────────
            def _dispatch_audit():
                try:
                    from apps.audit_logs.services.vendor import vendor_audit
                    if profile_created:
                        vendor_audit.log_vendor_provisioned(
                            actor=user,
                            vendor_profile=profile,
                            store_name=data.get("store_name", ""),
                            collections_count=len(collection_ids),
                            request=request,
                        )
                    else:
                        vendor_audit.log_vendor_profile_updated(
                            actor=user,
                            vendor_profile=profile,
                            new_values={
                                "store_name": data.get("store_name"),
                                "city": data.get("city"),
                                "state": data.get("state"),
                                "country": data.get("country"),
                                "collections_count": len(collection_ids),
                            },
                            request=request,
                        )
                except Exception as audit_exc:
                    logger.error(
                        "VendorProvisioningService.provision: Audit dispatch failed: %s",
                        audit_exc,
                    )

            transaction.on_commit(_dispatch_audit)

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
