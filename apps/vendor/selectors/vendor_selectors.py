# apps/vendor/selectors/vendor_selectors.py
"""
Vendor Domain Selectors — Read-only data fetching layer.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_vendor_profile_or_none(user) -> "VendorProfile | None":  # noqa: F821
    from apps.vendor.models import VendorProfile
    try:
        return (
            VendorProfile.objects
            .select_related("user", "setup_state")
            .get(user=user)
        )
    except VendorProfile.DoesNotExist:
        return None


async def aget_vendor_profile_or_none(user) -> "VendorProfile | None":  # noqa: F821
    from apps.vendor.models import VendorProfile
    try:
        return await (
            VendorProfile.objects
            .select_related("user")
            .aget(user=user)
        )
    except VendorProfile.DoesNotExist:
        return None


def get_vendor_setup_state(vendor_profile) -> "VendorSetupState | None":  # noqa: F821
    from apps.vendor.models import VendorSetupState
    try:
        return VendorSetupState.objects.get(vendor=vendor_profile)
    except VendorSetupState.DoesNotExist:
        return None


def get_vendor_quick_stats(user) -> dict[str, Any]:
    """Lightweight stats for JWT-embedded vendor data."""
    try:
        from apps.vendor.models import VendorProfile
        profile = VendorProfile.objects.values(
            "total_products",
            "total_sales",
            "total_revenue",
            "is_verified",
        ).get(user=user)
        return profile
    except Exception:
        return {
            "total_products": 0,
            "total_sales": 0,
            "total_revenue": 0,
            "is_verified": False,
        }
