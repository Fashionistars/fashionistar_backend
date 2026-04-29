# apps/vendor/apis/async_/dashboard_views.py
"""
Vendor Dashboard — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/vendor/

Authentication: JWT Bearer (apps.vendor.permissions.ninja_auth).

Architecture:
  ─ Read endpoints → VendorDashboardService (delegates to selectors).
  ─ Mutation endpoints live on the DRF sync surface under /api/v1/vendor/*.
    This router stays read-only so the async API contract remains clean.

IMPORTANT:
  sync_to_async is BANNED from this codebase.
  Prefer native async ORM for reads and sync services for writes.
"""
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.vendor.services.vendor_dashboard_service import VendorDashboardService
from apps.vendor.types.vendor_schemas import (
    SetupStateOut,
    VendorDashboardOut,
    VendorProfileOut,
)
from apps.common.roles import is_vendor_role

logger = logging.getLogger(__name__)

router = Router(tags=["Vendor — Async Dashboard"])

def _require_vendor_user(request):
    """Return the authenticated vendor user or raise a 403 error."""

    user = request.auth.user if hasattr(request.auth, "user") else request.auth
    if user is None or not is_vendor_role(getattr(user, "role", None)):
        raise HttpError(403, "Vendor access is required for this endpoint.")
    return user.vendor_profile.user


# ── Dashboard ──────────────────────────────────────────────────────────────


@router.get("/dashboard/", response=VendorDashboardOut)
async def get_vendor_dashboard(request):
    """
    GET /api/v1/ninja/vendor/dashboard/

    Full vendor dashboard: profile, analytics, setup state, recent orders,
    products, reviews, coupons, wallet, recent activity.
    """
    user = _require_vendor_user(request)
    try:
        summary = await VendorDashboardService.get_dashboard_summary(user)
        return summary
    except ValueError as exc:
        raise HttpError(404, str(exc))
    except Exception:
        logger.exception("get_vendor_dashboard: unexpected error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Dashboard fetch failed.")


# ── Profile ────────────────────────────────────────────────────────────────


@router.get("/profile/", response=VendorProfileOut)
async def get_vendor_profile_async(request):
    """
    GET /api/v1/ninja/vendor/profile/

    Async read of the vendor's own store profile.
    """
    from apps.vendor.selectors.vendor_selectors import aget_vendor_profile_or_none

    user = _require_vendor_user(request)
    profile = await aget_vendor_profile_or_none(user)
    if profile is None:
        raise HttpError(404, "Vendor setup is required before profile access.")

    try:
        setup_state = profile.setup_state
    except Exception:  # noqa: BLE001
        setup_state = None

    return VendorProfileOut(
        id=profile.pk,
        user_id=str(user.pk),
        user_email=getattr(user, "email", "") or "",
        store_name=profile.store_name,
        store_slug=profile.store_slug,
        tagline=profile.tagline,
        description=profile.description,
        logo_url=profile.logo_url,
        cover_url=profile.cover_url,
        city=profile.city,
        state=profile.state,
        country=profile.country,
        whatsapp=profile.whatsapp,
        instagram_url=profile.instagram_url,
        tiktok_url=profile.tiktok_url,
        twitter_url=profile.twitter_url,
        website_url=profile.website_url,
        total_products=profile.total_products,
        total_sales=profile.total_sales,
        total_revenue=float(profile.total_revenue),
        average_rating=float(profile.average_rating),
        review_count=profile.review_count,
        wallet_balance=float(profile.wallet_balance),
        is_verified=profile.is_verified,
        is_active=profile.is_active,
        is_featured=profile.is_featured,
        setup_state=(
            SetupStateOut(
                current_step=setup_state.current_step,
                profile_complete=setup_state.profile_complete,
                bank_details=setup_state.bank_details,
                id_verified=setup_state.id_verified,
                first_product=setup_state.first_product,
                onboarding_done=setup_state.onboarding_done,
                completion_percentage=setup_state.completion_percentage,
            )
            if setup_state is not None
            else None
        ),
    )


@router.get("/setup/", response=SetupStateOut)
async def get_vendor_setup_state_async(request):
    """Return onboarding/setup progress for the authenticated vendor."""

    from apps.vendor.selectors.vendor_selectors import (
        aget_vendor_profile_or_none,
        aget_vendor_setup_state_data,
    )

    user = _require_vendor_user(request)
    try:
        profile = await aget_vendor_profile_or_none(user)
        if profile is None:
            raise HttpError(404, "Vendor setup is required before setup-state access.")
        setup_state = await aget_vendor_setup_state_data(profile)
        return SetupStateOut(**setup_state)
    except HttpError:
        raise
    except Exception:
        logger.exception(
            "get_vendor_setup_state_async: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Setup state fetch failed.")


# ── Analytics ──────────────────────────────────────────────────────────────


@router.get("/analytics/")
async def get_vendor_analytics(request):
    """
    GET /api/v1/ninja/vendor/analytics/

    Full async analytics: revenue trends, top products, order counts, top categories.
    All 4 queries run concurrently via asyncio.gather() in VendorDashboardService.
    """
    user = _require_vendor_user(request)
    try:
        summary = await VendorDashboardService.get_analytics_summary(user)
        return {"status": "success", "data": summary}
    except ValueError as exc:
        raise HttpError(404, str(exc))
    except Exception:
        logger.exception("get_vendor_analytics: unexpected error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Analytics fetch failed.")
