# apps/vendor/admin_backend/selectors.py
"""
Admin-only async selectors for the vendor domain.

Anchor model: VendorProfile
Traversal: user (select_related), vendor_products, vendor_orders (prefetch)
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db.models import QuerySet, Count

logger = logging.getLogger(__name__)


def get_vendors_admin_qs(
    *,
    is_verified: Optional[bool] = None,
    is_active: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    ordering: str = "-created_at",
) -> QuerySet:
    """
    Base queryset for admin vendor list.
    Anchored on VendorProfile. select_related covers user.
    """
    from apps.vendor.models import VendorProfile

    qs = VendorProfile.objects.all_with_deleted().select_related(
        "user",
        "vendor_setup_state",
        "vendor_payout_profile",
    ).annotate(
        product_count=Count("vendor_products", distinct=True),
    )

    if is_verified is not None:
        qs = qs.filter(is_verified=is_verified)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    if is_featured is not None:
        qs = qs.filter(is_featured=is_featured)
    if country:
        qs = qs.filter(country__iexact=country)
    if search:
        qs = qs.filter(store_name__icontains=search) | qs.filter(
            user__email__icontains=search
        )

    return qs.order_by(ordering)


async def list_vendors_admin(
    *,
    is_verified: Optional[bool] = None,
    is_active: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    ordering: str = "-created_at",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Async paginated vendor list for admin dashboard."""
    from apps.common.pagination import async_ninja_paginate

    qs = get_vendors_admin_qs(
        is_verified=is_verified,
        is_active=is_active,
        is_featured=is_featured,
        country=country,
        search=search,
        ordering=ordering,
    )

    return await async_ninja_paginate(None, qs, page=page, page_size=page_size)


async def get_vendor_detail_admin(*, vendor_id: str):
    """
    Async vendor detail fetch.
    Anchored on VendorProfile. Traverses user, setup_state, payout_profile.
    """
    from apps.vendor.models import VendorProfile

    return await (
        VendorProfile.objects.all_with_deleted()
        .select_related(
            "user",
            "vendor_setup_state",
            "vendor_payout_profile",
        )
        .prefetch_related(
            "collections",
            "vendor_bank_accounts",
        )
        .aget(pk=vendor_id)
    )


async def get_vendor_products_admin(
    *,
    vendor_id: str,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """
    Async vendor products list from admin perspective.
    Anchored on Product via vendor_id FK.
    """
    from apps.common.pagination import async_ninja_paginate
    from apps.product.models import Product

    qs = (
        Product.objects.filter(vendor_id=vendor_id, is_deleted=False)
        .select_related("vendor")
        .prefetch_related("categories")
        .order_by("-created_at")
    )

    return await async_ninja_paginate(None, qs, page=page, page_size=page_size)


async def get_vendor_stats_admin() -> dict:
    """Aggregate vendor stats for KPI widget."""
    from apps.vendor.models import VendorProfile

    total = await VendorProfile.objects.acount()
    approved = await VendorProfile.objects.filter(is_verified=True).acount()
    suspended = await VendorProfile.objects.filter(
        is_active=False, is_deleted=False
    ).acount()
    featured = await VendorProfile.objects.filter(is_featured=True).acount()
    pending = await VendorProfile.objects.filter(
        is_verified=False, is_active=True, is_deleted=False
    ).acount()

    return {
        "total": total,
        "approved": approved,
        "pending": pending,
        "suspended": suspended,
        "featured": featured,
    }
