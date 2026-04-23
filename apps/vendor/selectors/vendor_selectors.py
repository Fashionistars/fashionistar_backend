# apps/vendor/selectors/vendor_selectors.py
"""
Vendor Domain Selectors — Read-only data fetching layer.

Rules:
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync selectors (no prefix) → used in DRF sync views.
  ─ Async selectors (prefix `a`) → used in Ninja async views.
  ─ ZERO sync_to_async() usage. All async selectors use Django 6.0 native
    async ORM: aget(), afilter(), acount(), aexists(), aget_or_create(),
    alist(), abulk_create(), prefetch_related_objects(), etc.
  ─ All reverse relationship traversals use pre-defined related_names
    from VendorProfile (e.g. vendor_orders, vendor_products, vendor_reviews).
"""
import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  SYNC selectors (DRF / admin / management commands)
# ══════════════════════════════════════════════════════════════════════


def get_vendor_profile_or_none(user) -> Optional["VendorProfile"]:  # noqa: F821
    """Return VendorProfile for ``user`` with related objects pre-loaded, or None."""
    from apps.vendor.models import VendorProfile
    try:
        return (
            VendorProfile.objects
            .select_related("user", "setup_state", "payout_profile")
            .prefetch_related("collections")
            .get(user=user)
        )
    except VendorProfile.DoesNotExist:
        return None


def get_vendor_setup_state(vendor_profile) -> Optional["VendorSetupState"]:  # noqa: F821
    """Return VendorSetupState for the given VendorProfile, or None."""
    from apps.vendor.models import VendorSetupState
    try:
        return VendorSetupState.objects.get(vendor=vendor_profile)
    except VendorSetupState.DoesNotExist:
        return None


def get_vendor_quick_stats(user) -> dict[str, Any]:
    """
    Lightweight stats for JWT-embedded claims / quick badges.
    Uses .values() to avoid deserializing the full model.
    """
    from apps.vendor.models import VendorProfile
    try:
        return VendorProfile.objects.values(
            "total_products",
            "total_sales",
            "total_revenue",
            "average_rating",
            "review_count",
            "is_verified",
            "wallet_balance",
        ).get(user=user)
    except Exception:
        return {
            "total_products": 0,
            "total_sales": 0,
            "total_revenue": Decimal("0"),
            "average_rating": Decimal("0"),
            "review_count": 0,
            "is_verified": False,
            "wallet_balance": Decimal("0"),
        }


def list_featured_vendors(limit: int = 10):
    """Return featured, active vendor profiles for the marketplace homepage."""
    from apps.vendor.models import VendorProfile
    return (
        VendorProfile.objects
        .filter(is_featured=True, is_active=True)
        .select_related("user")
        .prefetch_related("collections")
        .order_by("-average_rating")[:limit]
    )


# ══════════════════════════════════════════════════════════════════════
#  ASYNC selectors (Django-Ninja async router)
#  ── Only Django 6.0 native async ORM methods ──
#  ── ZERO sync_to_async() ──
# ══════════════════════════════════════════════════════════════════════


async def aget_vendor_profile_or_none(user) -> Optional["VendorProfile"]:  # noqa: F821
    """Async: return VendorProfile with key related objects, or None."""
    from apps.vendor.models import VendorProfile
    try:
        return await (
            VendorProfile.objects
            .select_related("user", "setup_state", "payout_profile")
            .aget(user=user)
        )
    except VendorProfile.DoesNotExist:
        return None


async def aget_vendor_setup_state_data(vendor_profile) -> dict[str, Any]:
    """
    Async: return setup state as a plain dict.
    Safe fallback if VendorSetupState row does not yet exist.
    """
    from apps.vendor.models import VendorSetupState
    try:
        setup = await VendorSetupState.objects.aget(vendor=vendor_profile)
        return {
            "current_step": setup.current_step,
            "profile_complete": setup.profile_complete,
            "bank_details": setup.bank_details,
            "id_verified": setup.id_verified,          # informational — KYC future sprint
            "first_product": setup.first_product,
            "onboarding_done": setup.onboarding_done,
            "completion_percentage": setup.completion_percentage,
        }
    except VendorSetupState.DoesNotExist:
        return {
            "current_step": 1,
            "profile_complete": False,
            "bank_details": False,
            "id_verified": False,
            "first_product": False,
            "onboarding_done": False,
            "completion_percentage": 0,
        }


async def aget_vendor_payout_profile_data(vendor_profile) -> dict[str, Any]:
    """Async: return payout profile as a safe plain dict (no encrypted fields exposed)."""
    from apps.vendor.models import VendorPayoutProfile
    try:
        payout = await VendorPayoutProfile.objects.aget(vendor=vendor_profile)
        return {
            "bank_name": payout.bank_name,
            "bank_code": payout.bank_code,
            "account_name": payout.account_name,
            "account_last4": payout.account_last4,
            "paystack_recipient_code": payout.paystack_recipient_code,
            "is_verified": payout.is_verified,
        }
    except VendorPayoutProfile.DoesNotExist:  # noqa: F821
        return {}


async def aget_vendor_recent_orders(vendor_profile, limit: int = 10) -> list[dict]:
    """
    Async: most recent N orders for this vendor.
    Uses vendor.vendor_orders reverse FK with Django 6.0 alist().
    """
    try:
        qs = (
            vendor_profile.vendor_orders
            .order_by("-date")
            .values("id", "total", "payment_status", "date", "order_status")[:limit]
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_recent_orders vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_products_summary(vendor_profile, limit: int = 10) -> list[dict]:
    """
    Async: top N products by stock_qty for the vendor dashboard.
    Uses vendor.vendor_products reverse FK.
    """
    try:
        qs = (
            vendor_profile.vendor_products
            .order_by("-date")
            .values("id", "title", "price", "stock_qty", "status")[:limit]
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_products_summary vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_reviews_summary(vendor_profile, limit: int = 5) -> list[dict]:
    """
    Async: recent reviews on vendor products.
    Traversal: vendor_products → review_product (Review model).
    """
    try:
        qs = (
            vendor_profile.vendor_products
            .values(
                "review_product__rating",
                "review_product__review",
                "review_product__date",
                "title",
            )
            .order_by("-review_product__date")[:limit]
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_reviews_summary vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_coupon_stats(vendor_profile) -> dict[str, Any]:
    """
    Async: coupon totals (active / inactive).
    Uses vendor.vendor_coupons reverse FK.
    """
    try:
        active_count   = await vendor_profile.vendor_coupons.filter(active=True).acount()
        inactive_count = await vendor_profile.vendor_coupons.filter(active=False).acount()
        return {"active": active_count, "inactive": inactive_count}
    except Exception as exc:
        logger.error("aget_vendor_coupon_stats vendor=%s: %s", vendor_profile.pk, exc)
        return {"active": 0, "inactive": 0}


async def aget_vendor_wallet_data(vendor_profile) -> dict[str, Any]:
    """
    Async: vendor wallet balance + recent transactions.
    Uses vendor.vendor_wallet_transactions reverse FK.
    """
    try:
        transactions = (
            vendor_profile.vendor_wallet_transactions
            .order_by("-date")
            .values("amount", "transaction_type", "date", "description")[:10]
        )
        tx_list = [row async for row in transactions]
        return {
            "balance": float(vendor_profile.wallet_balance),
            "recent_transactions": tx_list,
        }
    except Exception as exc:
        logger.error("aget_vendor_wallet_data vendor=%s: %s", vendor_profile.pk, exc)
        return {"balance": 0.0, "recent_transactions": []}
