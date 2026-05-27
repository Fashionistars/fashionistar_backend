# apps/vendor/admin_backend/services.py
"""
Admin-only service layer for the vendor domain.

All mutations:
  - transaction.atomic
  - event_bus.emit_on_commit() for all post-commit side effects
  - Never mutates financial fields directly (handled by wallet domain)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.events import event_bus

logger = logging.getLogger(__name__)


class AdminVendorService:
    """Admin-only orchestration for VendorProfile governance."""

    # ─────────────────────────────────────────────────── approve ──

    @classmethod
    @transaction.atomic
    def approve_vendor(cls, *, vendor_id: str, admin_user) -> "VendorProfile":
        """
        Approve a vendor application.
        Sets is_verified=True and emits vendor.approved on event bus.
        """
        from apps.vendor.models import VendorProfile

        vendor = VendorProfile.objects.select_related("user").get(pk=vendor_id)

        if vendor.is_verified:
            raise ValidationError(
                f"Vendor {vendor.store_name} is already approved."
            )

        vendor.is_verified = True
        vendor.is_active = True
        vendor.save(update_fields=["is_verified", "is_active", "updated_at"])

        logger.info(
            "Admin %s approved vendor %s (%s)",
            admin_user.pk,
            vendor.pk,
            vendor.store_name,
        )

        event_bus.emit_on_commit(
            "vendor.approved",
            vendor_id=str(vendor.pk),
            user_id=str(vendor.user_id),
            admin_user_id=str(admin_user.pk),
        )

        return vendor

    # ─────────────────────────────────────────────────── suspend ──

    @classmethod
    @transaction.atomic
    def suspend_vendor(
        cls, *, vendor_id: str, reason: str, admin_user
    ) -> "VendorProfile":
        """
        Suspend a vendor account.
        Sets is_active=False and emits vendor.suspended.
        """
        from apps.vendor.models import VendorProfile

        vendor = VendorProfile.objects.select_related("user").get(pk=vendor_id)

        if not vendor.is_active:
            raise ValidationError(
                f"Vendor {vendor.store_name} is already suspended."
            )

        vendor.is_active = False
        vendor.save(update_fields=["is_active", "updated_at"])

        logger.info(
            "Admin %s suspended vendor %s (reason: %s)",
            admin_user.pk,
            vendor.pk,
            reason,
        )

        event_bus.emit_on_commit(
            "vendor.suspended",
            vendor_id=str(vendor.pk),
            user_id=str(vendor.user_id),
            reason=reason,
            admin_user_id=str(admin_user.pk),
        )

        return vendor

    # ─────────────────────────────────────────────────── reactivate ──

    @classmethod
    @transaction.atomic
    def reactivate_vendor(cls, *, vendor_id: str, admin_user) -> "VendorProfile":
        """Reactivate a suspended vendor account."""
        from apps.vendor.models import VendorProfile

        vendor = VendorProfile.objects.select_related("user").get(pk=vendor_id)

        if vendor.is_active:
            raise ValidationError(
                f"Vendor {vendor.store_name} is already active."
            )

        vendor.is_active = True
        vendor.save(update_fields=["is_active", "updated_at"])

        logger.info(
            "Admin %s reactivated vendor %s", admin_user.pk, vendor.pk
        )

        event_bus.emit_on_commit(
            "vendor.reactivated",
            vendor_id=str(vendor.pk),
            user_id=str(vendor.user_id),
            admin_user_id=str(admin_user.pk),
        )

        return vendor

    # ─────────────────────────────────────────────────── reject ──

    @classmethod
    @transaction.atomic
    def reject_vendor(
        cls, *, vendor_id: str, reason: str, admin_user
    ) -> "VendorProfile":
        """
        Reject a vendor application.
        Resets is_verified=False, is_active=False and emits vendor.rejected.
        """
        from apps.vendor.models import VendorProfile

        vendor = VendorProfile.objects.select_related("user").get(pk=vendor_id)

        vendor.is_verified = False
        vendor.is_active = False
        vendor.save(update_fields=["is_verified", "is_active", "updated_at"])

        logger.info(
            "Admin %s rejected vendor %s (reason: %s)",
            admin_user.pk,
            vendor.pk,
            reason,
        )

        event_bus.emit_on_commit(
            "vendor.rejected",
            vendor_id=str(vendor.pk),
            user_id=str(vendor.user_id),
            reason=reason,
            admin_user_id=str(admin_user.pk),
        )

        return vendor

    # ─────────────────────────────────────────────────── commission ──

    @classmethod
    @transaction.atomic
    def update_vendor_commission(
        cls,
        *,
        vendor_id: str,
        commission_rate: Decimal,
        admin_user,
    ) -> "VendorProfile":
        """
        Update the default platform commission rate for a vendor.
        Note: individual product commission_rate snapshots are unchanged.
        """
        from apps.vendor.models import VendorProfile

        if not (Decimal("0") <= commission_rate <= Decimal("100")):
            raise ValidationError("Commission rate must be between 0 and 100.")

        vendor = VendorProfile.objects.get(pk=vendor_id)
        old_rate = getattr(vendor, "commission_rate", None)

        # Update the vendor-level default commission rate
        VendorProfile.objects.filter(pk=vendor_id).update(
            commission_rate=commission_rate
        )

        logger.info(
            "Admin %s updated vendor %s commission: %s → %s",
            admin_user.pk,
            vendor_id,
            old_rate,
            commission_rate,
        )

        event_bus.emit_on_commit(
            "vendor.commission_updated",
            vendor_id=str(vendor_id),
            old_rate=str(old_rate),
            new_rate=str(commission_rate),
            admin_user_id=str(admin_user.pk),
        )

        return vendor

    # ─────────────────────────────────────────────────── feature ──

    @classmethod
    @transaction.atomic
    def toggle_vendor_featured(
        cls, *, vendor_id: str, featured: bool, admin_user
    ) -> "VendorProfile":
        """Toggle a vendor's featured status on the storefront."""
        from apps.vendor.models import VendorProfile

        vendor = VendorProfile.objects.get(pk=vendor_id)
        vendor.is_featured = featured
        vendor.save(update_fields=["is_featured", "updated_at"])

        event_bus.emit_on_commit(
            "vendor.featured_toggled",
            vendor_id=str(vendor.pk),
            featured=featured,
            admin_user_id=str(admin_user.pk),
        )

        return vendor
