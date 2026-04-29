# apps/client/apis/async_/dashboard_views.py
"""
Client Dashboard — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/client/

This router is intentionally read-only. Transaction-heavy writes remain on
the DRF sync surface under /api/v1/client/*.

Authentication: JWT Bearer (via NinjaJWT or shared auth middleware).
"""
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.client.services.client_dashboard_service import ClientDashboardService
from apps.client.types.client_schemas import (
    AddressOut,
    DashboardOut,
    ProfileOut,
)
from apps.common.roles import is_client_role

logger = logging.getLogger(__name__)

# This router is registered on the root Ninja API inside `backend/urls.py`
# under the /api/v1/ninja/client/ prefix.
router = Router(tags=["Client — Async Dashboard"])

def _require_client_user(request):
    """Return the authenticated client user or raise a 403 error."""

    user = request.auth
    if user is None or not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access is required for this endpoint.")
    return user


# ── Dashboard Summary ──────────────────────────────────────────────────

@router.get("/dashboard/", response=DashboardOut)
async def get_client_dashboard(request):
    """
    GET /api/v1/ninja/client/dashboard/

    Returns the complete dashboard payload for the authenticated client.
    Aggregates profile data, analytics, and AI recommendations.
    """
    user = _require_client_user(request)
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
    from apps.client.selectors.client_selectors import (
        aget_client_profile_or_none,
        alist_client_addresses,
    )
    from apps.client.services.client_provisioning_service import ClientProvisioningService

    user = _require_client_user(request)
    profile = await aget_client_profile_or_none(user)
    if profile is None:
        profile = await ClientProvisioningService.aprovision(user)

    addresses = await alist_client_addresses(profile)

    return ProfileOut(
        id=profile.pk,
        user_id=str(user.pk),
        user_email=getattr(user, "email", "") or "",
        bio=profile.bio,
        default_shipping_address=profile.default_shipping_address,
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


@router.get("/addresses/", response=list[AddressOut])
async def list_client_addresses_async(request):
    """Return the authenticated client's saved addresses."""

    from apps.client.selectors.client_selectors import (
        aget_client_profile_or_none,
        alist_client_addresses,
    )
    from apps.client.services.client_provisioning_service import ClientProvisioningService

    user = _require_client_user(request)
    profile = await aget_client_profile_or_none(user)
    if profile is None:
        profile = await ClientProvisioningService.aprovision(user)
    return await alist_client_addresses(profile)
