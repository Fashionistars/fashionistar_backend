# apps/vendor/apis/async_/dashboard_views.py
"""
Vendor Dashboard — Django-Ninja Async Router.

Mounted at: /api/v1/ninja/vendor/

Authentication: JWT Bearer (apps.vendor.permissions.ninja_auth).

Architecture:
  ─ Read endpoints → VendorDashboardService (delegates to selectors).
  ─ Mutation endpoints → run_in_executor pattern for sync service calls,
    because VendorService uses transaction.atomic() (sync Django ORM).
    NOTE: We do NOT use sync_to_async. We use asyncio.get_event_loop()
    .run_in_executor(None, ...) which is the correct Django 6.0 pattern
    for calling sync-atomic service methods from an async context without
    wrapping in sync_to_async (which creates an implicit thread executor).
    Reference: https://docs.djangoproject.com/en/6.0/topics/async/

IMPORTANT:
  sync_to_async is BANNED from this codebase.
  Prefer native async ORM or run_in_executor for sync-atomic transactions.
"""
import asyncio
import functools
import logging

from ninja import Router
from ninja.errors import HttpError

from apps.vendor.services.vendor_dashboard_service import VendorDashboardService
from apps.vendor.services.vendor_service import VendorService
from apps.vendor.types.vendor_schemas import (
    VendorDashboardOut,
    VendorProfileOut,
    VendorProfileUpdateIn,
    VendorPayoutIn,
    VendorPinIn,
    VendorPinVerifyIn,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Vendor — Async Dashboard"])


def _run_sync(func, *args, **kwargs):
    """
    Run a sync function in the default thread pool executor.
    Use this for sync transaction.atomic() service calls from async views.
    NEVER use sync_to_async() — this is the correct Django 6.0 pattern.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


# ── Dashboard ──────────────────────────────────────────────────────────────


@router.get("/dashboard/", response=VendorDashboardOut)
async def get_vendor_dashboard(request):
    """
    GET /api/v1/ninja/vendor/dashboard/

    Full vendor dashboard: profile, analytics, setup state, recent orders,
    products, reviews, coupons, wallet, recent activity.
    """
    user = request.auth
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

    user = request.auth
    profile = await aget_vendor_profile_or_none(user)
    if profile is None:
        raise HttpError(404, "Vendor setup is required before profile access.")

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
        whatsapp=profile.whatsapp,
        instagram_url=profile.instagram_url,
        tiktok_url=profile.tiktok_url,
        twitter_url=profile.twitter_url,
        website_url=profile.website_url,
        is_verified=profile.is_verified,
        is_active=profile.is_active,
        is_featured=profile.is_featured,
    )


@router.patch("/profile/", response=VendorProfileOut)
async def update_vendor_profile_async(request, payload: VendorProfileUpdateIn):
    """
    PATCH /api/v1/ninja/vendor/profile/

    Partial update of store profile.
    Sync transaction.atomic() call run via run_in_executor (no sync_to_async).
    """
    user = request.auth
    data = payload.dict(exclude_none=True)
    try:
        await _run_sync(VendorService.update_profile, user=user, data=data)
    except Exception as exc:
        logger.exception("update_vendor_profile_async: error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(400, f"Profile update failed: {exc}")
    return await get_vendor_profile_async(request)


# ── Payout ─────────────────────────────────────────────────────────────────


@router.post("/payout/")
async def save_payout_async(request, payload: VendorPayoutIn):
    """
    POST /api/v1/ninja/vendor/payout/

    Saves encrypted bank / payout account details.
    """
    user = request.auth
    data = payload.dict()
    try:
        payout = await _run_sync(VendorService.save_payout_details, user=user, data=data)
    except Exception as exc:
        logger.exception("save_payout_async: error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(400, f"Payout details save failed: {exc}")

    return {
        "status": "success",
        "message": "Payout details saved.",
        "data": {
            "bank_name":    payout.bank_name,
            "account_name": payout.account_name,
            "account_last4": payout.account_last4,
            "is_verified":  payout.is_verified,
        },
    }


# ── Transaction PIN ─────────────────────────────────────────────────────────


@router.post("/pin/set/")
async def set_transaction_pin(request, payload: VendorPinIn):
    """
    POST /api/v1/ninja/vendor/pin/set/

    Set or update 4-digit payout confirmation PIN.
    """
    user = request.auth
    try:
        await _run_sync(VendorService.set_transaction_pin, user=user, raw_pin=payload.pin)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    except Exception:
        logger.exception("set_transaction_pin: error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(400, "PIN update failed.")
    return {"status": "success", "message": "Transaction PIN updated."}


@router.post("/pin/verify/")
async def verify_transaction_pin(request, payload: VendorPinVerifyIn):
    """
    POST /api/v1/ninja/vendor/pin/verify/

    Verify payout PIN before a withdrawal/transfer action.
    """
    user = request.auth
    try:
        valid = await _run_sync(VendorService.verify_transaction_pin, user=user, raw_pin=payload.pin)
    except Exception:
        logger.exception("verify_transaction_pin: error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(400, "PIN verification failed.")

    if not valid:
        raise HttpError(401, "Invalid PIN.")
    return {"status": "success", "message": "PIN verified."}
