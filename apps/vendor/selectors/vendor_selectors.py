# apps/vendor/selectors/vendor_selectors.py
"""
Vendor Domain Selectors — Read-only data fetching layer.

Architecture Rules (NON-NEGOTIABLE):
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync selectors (no prefix)  → used in DRF sync views / admin.
  ─ Async selectors (prefix `a`) → used in Django-Ninja async views.
  ─ ZERO sync_to_async() usage.
  ─ All async selectors use Django 6.0 native async ORM.
  ─ Query logic lives on the MODEL (DB layer) via classmethods.
    These selectors are thin wrappers that delegate to those methods.

Reverse FK / related-name traversal map for this domain:
  user.vendor_profile                 → VendorProfile (OneToOne)
  vendor.vendor_orders.filter(...)    → CartOrder rows
  vendor.vendor_products.filter(...)  → Product rows
  vendor.vendor_reviews.filter(...)   → Review rows
  vendor.vendor_coupons.filter(...)   → Coupon rows
  vendor.vendor_wallet_transactions.filter(...) → WalletTransaction rows
  vendor.setup_state                  → VendorSetupState (OneToOne)
  vendor.vendor_payout_profile        → VendorPayoutProfile (OneToOne)

Google-style docstrings required for all non-trivial functions.
"""

import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  SYNC selectors  (DRF views / admin / management commands)
# ══════════════════════════════════════════════════════════════════════


def get_vendor_profile_or_none(user) -> Optional["VendorProfile"]:  # noqa: F821
    """
    Return VendorProfile for ``user`` with key related objects pre-loaded, or None.

    Traversal: user.vendor_profile (OneToOne).

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        VendorProfile or None.
    """
    from apps.vendor.models import VendorProfile
    try:
        return (
            VendorProfile.objects
            .select_related("user", "vendor_setup_state", "vendor_payout_profile")
            .prefetch_related("collections")
            .get(user=user)
        )
    except VendorProfile.DoesNotExist:
        return None


def get_vendor_setup_state(vendor_profile) -> Optional["VendorSetupState"]:  # noqa: F821
    """
    Return VendorSetupState for the given VendorProfile, or None.

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        VendorSetupState or None.
    """
    from apps.vendor.models import VendorSetupState
    try:
        return VendorSetupState.objects.get(vendor=vendor_profile)
    except VendorSetupState.DoesNotExist:
        return None


def get_vendor_quick_stats(user) -> dict[str, Any]:
    """
    Lightweight stats for JWT-embedded claims / quick badge counts.

    Uses .values() to avoid deserializing the full model — single query.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        dict with total_products, total_sales, total_revenue, average_rating,
        review_count, is_verified, wallet_balance.
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


def get_vendor_dashboard_snapshot(user) -> dict[str, Any]:
    """
    Sync: return full vendor dashboard snapshot as a plain dict.

    Delegates to VendorProfile.get_full_dashboard_snapshot() at the DB layer.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        dict with all vendor dashboard fields.
    """
    from apps.vendor.models import VendorProfile
    return VendorProfile.get_full_dashboard_snapshot(user)


def list_featured_vendors(limit: int = 10):
    """
    Return featured, active vendor profiles for the marketplace homepage.

    Args:
        limit: Max number of profiles to return (default 10).

    Returns:
        QuerySet[VendorProfile] ordered by average_rating descending.
    """
    from apps.vendor.models import VendorProfile
    return (
        VendorProfile.objects
        .filter(is_featured=True, is_active=True)
        .select_related("user")
        .prefetch_related("collections")
        .order_by("-average_rating")[:limit]
    )


# ══════════════════════════════════════════════════════════════════════
#  ASYNC selectors  (Django-Ninja async router)
#  ── Only Django 6.0 native async ORM — ZERO sync_to_async ──
# ══════════════════════════════════════════════════════════════════════


async def aget_vendor_profile_or_none(user) -> Optional["VendorProfile"]:  # noqa: F821
    """
    Async: return VendorProfile with key related objects, or None.

    Traversal: user.vendor_profile (OneToOne via aget).

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        VendorProfile or None.
    """
    from apps.vendor.models import VendorProfile
    try:
        return await (
            VendorProfile.objects
            .select_related("user", "vendor_setup_state", "vendor_payout_profile")
            .aget(user=user)
        )
    except VendorProfile.DoesNotExist:
        return None


async def aget_vendor_dashboard_snapshot(user) -> dict[str, Any]:
    """
    Async: return full vendor dashboard snapshot as a plain dict.

    Delegates to VendorProfile.aget_full_dashboard_snapshot() at the DB layer.

    Args:
        user: Authenticated UnifiedUser instance.

    Returns:
        dict with all vendor dashboard fields.
    """
    from apps.vendor.models import VendorProfile
    return await VendorProfile.aget_full_dashboard_snapshot(user)


async def aget_vendor_setup_state_data(vendor_profile) -> dict[str, Any]:
    """
    Async: return setup state as a plain dict.

    Safe fallback if VendorSetupState row does not yet exist.

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        dict with current_step, profile_complete, bank_details, id_verified,
        first_product, onboarding_done, completion_percentage.
    """
    from apps.vendor.models import VendorSetupState
    try:
        setup = await VendorSetupState.objects.aget(vendor=vendor_profile)
        # Compute % from milestones: profile_complete, bank_details, id_verified,
        # first_product, onboarding_done  (each = 20% of 100%)
        milestones = [
            setup.profile_complete,
            setup.bank_details,
            setup.id_verified,
            setup.first_product,
            setup.onboarding_done,
        ]
        computed_pct = sum(1 for m in milestones if m) * 20
        return {
            "current_step":          setup.current_step,
            "profile_complete":      setup.profile_complete,
            "bank_details":          setup.bank_details,
            "id_verified":           setup.id_verified,
            "first_product":         setup.first_product,
            "onboarding_done":       setup.onboarding_done,
            "completion_percentage": computed_pct,
        }
    except VendorSetupState.DoesNotExist:
        return {
            "current_step":          1,
            "profile_complete":      False,
            "bank_details":          False,
            "id_verified":           False,
            "first_product":         False,
            "onboarding_done":       False,
            "completion_percentage": 0,
        }


async def aget_vendor_payout_profile_data(vendor_profile) -> dict[str, Any]:
    """
    Async: return payout profile as a safe plain dict (no encrypted fields exposed).

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        dict with bank_name, bank_code, account_name, account_last4,
        paystack_recipient_code, is_verified.
    """
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


async def aget_vendor_order_stats(vendor_profile) -> dict[str, Any]:
    """
    Async: aggregate order stats for a vendor.

    Delegates to VendorProfile.aget_order_stats_from_db() at the DB layer.

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        dict with total_orders, total_revenue, pending_count, active_count.
    """
    from apps.vendor.models import VendorProfile
    return await VendorProfile.aget_order_stats_from_db(vendor_profile)


async def aget_vendor_recent_orders(vendor_profile, limit: int = 10) -> list[dict]:
    """
    Async: most recent N orders for this vendor.

    Delegates to VendorProfile.aget_recent_orders_from_db() at the DB layer.

    Args:
        vendor_profile: VendorProfile instance.
        limit: Max rows to return (default 10).

    Returns:
        list[dict] with id, total, payment_status, date, order_status.
    """
    from apps.vendor.models import VendorProfile
    return await VendorProfile.aget_recent_orders_from_db(vendor_profile, limit=limit)


async def aget_vendor_products_summary(vendor_profile, limit: int = 10) -> list[dict]:
    """
    Async: top N products by creation date for the vendor dashboard.

    Delegates to VendorProfile.aget_product_summary_from_db() at the DB layer.

    Args:
        vendor_profile: VendorProfile instance.
        limit: Max rows to return (default 10).

    Returns:
        list[dict] with id, title, price, stock_qty, status.
    """
    from apps.vendor.models import VendorProfile
    return await VendorProfile.aget_product_summary_from_db(vendor_profile, limit=limit)


async def aget_vendor_wallet_data(vendor_profile) -> dict[str, Any]:
    """
    Async: vendor wallet balance + recent transactions.

    Balance delegates to VendorProfile.aget_wallet_balance_from_db().
    Transaction list uses reverse FK async iteration.

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        dict with balance (float) and recent_transactions (list[dict]).
    """
    from apps.vendor.models import VendorProfile
    try:
        balance = await VendorProfile.aget_wallet_balance_from_db(vendor_profile)
        from django.db.models import Q
        from apps.transactions.models import Transaction

        transactions = (
            Transaction.objects.filter(
                Q(from_user_id=vendor_profile.user_id)
                | Q(to_user_id=vendor_profile.user_id)
            )
            .order_by("-created_at")
            .values(
                "amount",
                "transaction_type",
                "status",
                "direction",
                "created_at",
                "description",
            )[:10]
        )
        tx_list = [row async for row in transactions]
        return {
            "balance": balance,
            "recent_transactions": tx_list,
        }
    except Exception as exc:
        logger.error("aget_vendor_wallet_data vendor=%s: %s", vendor_profile.pk, exc)
        return {"balance": 0.0, "recent_transactions": []}


async def aget_vendor_reviews_summary(vendor_profile, limit: int = 5) -> list[dict]:
    """
    Async: recent reviews on vendor products.

    Traversal: vendor_products → review_product (Review model).

    Args:
        vendor_profile: VendorProfile instance.
        limit: Max rows to return (default 5).

    Returns:
        list[dict] with review_product__rating, review_product__review,
        review_product__date, title.
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

    Delegates to VendorProfile.aget_coupon_stats_from_db() at the DB layer.

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        dict with active (int) and inactive (int).
    """
    from apps.vendor.models import VendorProfile
    return await VendorProfile.aget_coupon_stats_from_db(vendor_profile)


async def aget_vendor_revenue_trends(vendor_profile, months: int = 6) -> list[dict]:
    """
    Async: monthly revenue over the last N months.

    Uses vendor.vendor_orders reverse FK with Django 6.0 async ORM.

    Args:
        vendor_profile: VendorProfile instance.
        months: Number of trailing months to include (default 6).

    Returns:
        list[dict] with month (int) and total_revenue (Decimal).
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models import Sum
    from django.db.models.functions import ExtractMonth
    try:
        cutoff = timezone.now() - timedelta(days=months * 30)
        qs = (
            vendor_profile.vendor_orders
            .filter(
                status__in=vendor_profile.revenue_order_statuses,
                created_at__gte=cutoff,
            )
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(total_revenue=Sum("total_amount"))
            .order_by("month")
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_revenue_trends vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_top_selling_products(vendor_profile, limit: int = 5) -> list[dict]:
    """
    Async: top-selling products by total quantity sold.

    Delegates to VendorProfile.aget_top_selling_products_from_db() at the DB layer.

    Args:
        vendor_profile: VendorProfile instance.
        limit: Max rows to return (default 5).

    Returns:
        list[dict] with id, title, price, stock_qty, total_qty.
    """
    from apps.vendor.models import VendorProfile
    return await VendorProfile.aget_top_selling_products_from_db(vendor_profile, limit=limit)


async def aget_vendor_order_status_counts(vendor_profile) -> list[dict]:
    """
    Async: count of orders grouped by status.

    Uses vendor.vendor_orders reverse FK.

    Args:
        vendor_profile: VendorProfile instance.

    Returns:
        list[dict] with status (str) and count (int).
    """
    from django.db.models import Count
    try:
        qs = (
            vendor_profile.vendor_orders
            .values("status")
            .annotate(count=Count("id"))
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_order_status_counts vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_top_categories(vendor_profile, limit: int = 5) -> list[dict]:
    """
    Async: top product categories by sales revenue.

    Traversal: vendor_products → categories__name / cart_order_product_snapshots.

    Args:
        vendor_profile: VendorProfile instance.
        limit: Max rows to return (default 5).

    Returns:
        list[dict] with categories__name (str) and sales (Decimal).
    """
    from django.db.models import Sum
    try:
        qs = (
            vendor_profile.vendor_products
            .values("categories__name")
            .annotate(sales=Sum("cart_order_product_snapshots__line_total"))
            .order_by("-sales")[:limit]
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_top_categories vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_low_stock_alerts(vendor_profile, threshold: int = 5) -> list[dict]:
    """
    Async: products with stock_qty below the given threshold.

    Traversal: vendor_products reverse FK (Product model).

    Args:
        vendor_profile: VendorProfile instance.
        threshold: Minimum stock quantity — products below this value are returned (default 5).

    Returns:
        list[dict] with title (str) and stock_qty (int), ordered by stock_qty ascending.
    """
    try:
        qs = (
            vendor_profile.vendor_products
            .filter(stock_qty__lt=threshold)
            .order_by("stock_qty")
            .values("title", "stock_qty")[:20]
        )
        return [row async for row in qs]
    except Exception as exc:
        logger.error("aget_vendor_low_stock_alerts vendor=%s: %s", vendor_profile.pk, exc)
        return []


async def aget_vendor_setup_state_data_extended(vendor_profile) -> dict:
    """Alias — delegates to aget_vendor_setup_state_data (backward compat)."""
    return await aget_vendor_setup_state_data(vendor_profile)
