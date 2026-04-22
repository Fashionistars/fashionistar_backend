# apps/vendor/apis/async_/dashboard_views.py
"""
Vendor Dashboard — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/vendor/

Authentication: JWT Bearer.
"""
import logging

from ninja import Router
from ninja.security import HttpBearer

from apps.vendor.services.vendor_dashboard_service import VendorDashboardService
from apps.vendor.services.vendor_service import VendorService
from apps.vendor.types.vendor_schemas import (
    VendorDashboardOut,
    VendorProfileOut,
    VendorProfileUpdateIn,
    VendorPayoutIn,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Vendor — Async Dashboard"])


@router.get("/dashboard/", response=VendorDashboardOut, auth=HttpBearer())
async def get_vendor_dashboard(request):
    """
    GET /api/v1/ninja/vendor/dashboard/

    Returns the full vendor dashboard: profile, analytics, setup state,
    and recent activity feed.
    """
    user = request.auth
    summary = await VendorDashboardService.get_dashboard_summary(user)
    return summary


@router.get("/profile/", response=VendorProfileOut, auth=HttpBearer())
async def get_vendor_profile_async(request):
    """
    GET /api/v1/ninja/vendor/profile/

    Async read of the vendor's own store profile.
    """
    from apps.vendor.selectors.vendor_selectors import aget_vendor_profile_or_none
    from apps.vendor.services.vendor_provisioning_service import VendorProvisioningService
    from asgiref.sync import sync_to_async

    user = request.auth
    profile = await aget_vendor_profile_or_none(user)
    if profile is None:
        profile = await sync_to_async(VendorProvisioningService.provision)(user)

    return VendorProfileOut(
        id=profile.pk,
        user_id=str(user.pk),
        store_name=profile.store_name,
        store_slug=profile.store_slug,
        tagline=profile.tagline,
        description=profile.description,
        logo_url=profile.logo_url,
        cover_url=profile.cover_url,
        city=profile.city,
        state=profile.state,
        country=profile.country,
        instagram_url=profile.instagram_url,
        tiktok_url=profile.tiktok_url,
        twitter_url=profile.twitter_url,
        website_url=profile.website_url,
        is_verified=profile.is_verified,
        is_active=profile.is_active,
        is_featured=profile.is_featured,
    )


@router.patch("/profile/", response=VendorProfileOut, auth=HttpBearer())
async def update_vendor_profile_async(request, payload: VendorProfileUpdateIn):
    """
    PATCH /api/v1/ninja/vendor/profile/

    Async partial update of store profile.
    """
    from asgiref.sync import sync_to_async

    user = request.auth
    data = payload.dict(exclude_none=True)
    await sync_to_async(VendorService.update_profile)(user=user, data=data)
    return await get_vendor_profile_async(request)


@router.post("/payout/", auth=HttpBearer())
async def save_payout_async(request, payload: VendorPayoutIn):
    """
    POST /api/v1/ninja/vendor/payout/

    Saves encrypted bank / payout account details.
    """
    from asgiref.sync import sync_to_async

    user = request.auth
    data = payload.dict()
    payout = await sync_to_async(VendorService.save_payout_details)(user=user, data=data)
    return {
        "status": "success",
        "message": "Payout details saved.",
        "data": {
            "bank_name": payout.bank_name,
            "account_name": payout.account_name,
            "account_last4": payout.account_last4,
            "is_verified": payout.is_verified,
        },
    }
