# apps/client/apis/async_/dashboard_views.py
"""
Client Dashboard — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/client/

Read handlers use native async ORM.
Transaction-heavy writes stay in sync services and are called explicitly
through a thread-pool bridge during transition. This avoids `sync_to_async`
and keeps atomic write logic inside the existing sync service layer.

Authentication: JWT Bearer (via NinjaJWT or shared auth middleware).
"""
import asyncio
import functools
import logging

from ninja import Router

from apps.client.services.client_dashboard_service import ClientDashboardService
from apps.client.services.client_profile_service import ClientProfileService
from apps.client.types.client_schemas import (
    AddressIn,
    DashboardOut,
    ProfileOut,
    ProfileUpdateIn,
)

logger = logging.getLogger(__name__)

# This router is registered on the root Ninja API inside `backend/urls.py`
# under the /api/v1/ninja/client/ prefix.
router = Router(tags=["Client — Async Dashboard"])


def _run_sync(func, *args, **kwargs):
    """
    Execute a synchronous service method without `sync_to_async`.

    This is only used for transitional sync write paths that still depend on
    `transaction.atomic()` in the service layer.
    """
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


# ── Dashboard Summary ──────────────────────────────────────────────────

@router.get("/dashboard/", response=DashboardOut)
async def get_client_dashboard(request):
    """
    GET /api/v1/ninja/client/dashboard/

    Returns the complete dashboard payload for the authenticated client.
    Aggregates profile data, analytics, and AI recommendations.
    """
    user = request.auth  # NinjaJWT sets request.auth to the user instance
    summary = await ClientDashboardService.get_dashboard_summary(user)
    return summary


# ── Profile ────────────────────────────────────────────────────────────

@router.get("/profile/", response=ProfileOut)
async def get_client_profile_async(request):
    """
    GET /api/v1/ninja/client/profile/

    Async read of the client's own profile. Mirrors the sync endpoint
    but is served from the ASGI (Uvicorn) worker — higher throughput.
    """
    from apps.client.selectors.client_selectors import aget_client_profile_or_none
    from apps.client.services.client_provisioning_service import ClientProvisioningService

    user = request.auth
    profile = await aget_client_profile_or_none(user)
    if profile is None:
        profile = await ClientProvisioningService.aprovision(user)

    # Build addresses list
    from apps.client.models import ClientAddress
    addresses = [
        addr async for addr in
        ClientAddress.objects.filter(client=profile, is_deleted=False)
        .order_by("-is_default", "-created_at")
    ]

    return ProfileOut(
        id=profile.pk,
        user_id=str(user.pk),
        bio=profile.bio,
        preferred_size=profile.preferred_size,
        style_preferences=profile.style_preferences,
        favourite_colours=profile.favourite_colours,
        country=profile.country,
        state=profile.state,
        is_profile_complete=profile.is_profile_complete,
        total_orders=profile.total_orders,
        total_spent_ngn=profile.total_spent_ngn,
        email_notifications_enabled=profile.email_notifications_enabled,
        sms_notifications_enabled=profile.sms_notifications_enabled,
        addresses=[
            {
                "id": a.pk,
                "label": a.label,
                "full_name": a.full_name,
                "phone": a.phone,
                "street_address": a.street_address,
                "city": a.city,
                "state": a.state,
                "country": a.country,
                "postal_code": a.postal_code,
                "is_default": a.is_default,
            }
            for a in addresses
        ],
    )


@router.patch("/profile/", response=ProfileOut)
async def update_client_profile_async(request, payload: ProfileUpdateIn):
    """
    PATCH /api/v1/ninja/client/profile/

    Async partial update of the client profile.
    Only sends fields that are not None.
    """
    user = request.auth
    data = payload.dict(exclude_none=True)

    profile = await _run_sync(ClientProfileService.update_profile, user=user, data=data)

    return await get_client_profile_async(request)
