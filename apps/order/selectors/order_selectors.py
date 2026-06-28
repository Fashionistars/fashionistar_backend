# apps/order/selectors/order_selectors.py
"""
Order Domain Selectors — Read-only data fetching layer.

Architecture Rules (NON-NEGOTIABLE):
  ─ Selectors NEVER mutate data. All mutations live in services/.
  ─ Sync selectors (no prefix) → used in DRF sync views.
  ─ Async selectors (prefix `a`) → used in Django-Ninja async views.
  ─ ZERO sync_to_async() usage.
  ─ All async selectors use Django 6.0 native async ORM:
      aget()               → single object lookup
      acount()             → COUNT aggregate
      aexists()            → EXISTS check
      aaggregate()         → SUM/COUNT/AVG aggregates
      [row async for qs]   → async iteration over QuerySet
      aprefetch_related_objects([obj], ...) → async prefetch after aget()
  ─ select_related() / prefetch_related() are chain-safe on async QuerySets.
  ─ All reverse FK traversals use defined related_names:
      user.user_orders         → Order rows for this client user
      vendor.vendor_orders     → Order rows for this vendor
      order.order_items        → OrderItem rows for this order
      order.order_status_history → OrderStatusHistory rows
      order.order_idempotency_record → OneToOne guard

Google-style docstrings are required for every non-trivial function.
"""

import logging
from typing import Any, Optional

from django.db.models import Prefetch
from django.db.models import aprefetch_related_objects

from apps.order.models import Order, CartOrderItem as OrderItem

logger = logging.getLogger(__name__)


def _normalize_order_list_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize database rows into the frontend/Ninja order-list contract.

    Args:
        row: Dictionary returned by ``QuerySet.values()``.

    Returns:
        A JSON-ready row with stable money strings and compatibility fields.
    """
    total = row.get("total_amount") or 0
    subtotal = row.get("subtotal") or total
    status_value = row.get("status") or "pending_payment"
    return {
        **row,
        "id": str(row.get("id")),
        "payment_status": row.get("payment_status") or (
            "paid" if status_value in {"payment_confirmed", "processing", "shipped", "delivered", "completed"} else "unpaid"
        ),
        "escrow_status": row.get("escrow_status") or (
            "released" if status_value == "completed" else "held"
        ),
        "item_count": row.get("item_count") or 0,
        "subtotal": str(subtotal),
        "final_total": str(total),
        "total_amount": str(total),
        "requires_measurement": bool(row.get("requires_measurement", False)),
    }


# ══════════════════════════════════════════════════════════════════════
#  SYNC selectors  (DRF views / admin / management commands)
# ══════════════════════════════════════════════════════════════════════


def get_user_orders(user_id, status: str | None = None):
    """
    Return the authenticated client's order list, most recent first.

    Prefetches order items + product thumbnails + status history to
    eliminate N+1 queries in DRF serializers.

    Args:
        user_id: PK of the authenticated UnifiedUser.
        status: Optional OrderStatus string to filter (e.g. "pending_payment").

    Returns:
        QuerySet[Order] ordered by -created_at.
    """
    qs = (
        Order.objects.filter(user_id=user_id)
        .prefetch_related(
            Prefetch(
                "cart_order_items",
                queryset=OrderItem.objects.select_related(
                    "product", "variant", "vendor"
                ),
            ),
            "order_status_history",
            "payment_records",
            "commercial_transition_logs",
        )
        .select_related("vendor", "delivery_courier")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_vendor_orders(vendor_id, status: str | None = None):
    """
    Return order list for a vendor profile, most recent first.

    Args:
        vendor_id: PK of VendorProfile.
        status: Optional OrderStatus filter.

    Returns:
        QuerySet[Order] filtered by vendor, ordered by -created_at.
    """
    qs = (
        Order.objects.filter(vendor_id=vendor_id)
        .prefetch_related(
            Prefetch(
                "cart_order_items",
                queryset=OrderItem.objects.select_related("product", "variant"),
            ),
            "order_status_history",
            "payment_records",
            "commercial_transition_logs",
        )
        .select_related("user", "delivery_courier")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_order_by_id_for_user(order_id, user_id) -> Optional[Order]:
    """
    Return a single order for a client user with full detail prefetched.

    Args:
        order_id: PK of the Order.
        user_id: PK of the authenticated user (ownership guard).

    Returns:
        Order instance or None if not found / not owned.
    """
    try:
        return (
            Order.objects
            .prefetch_related(
                Prefetch(
                    "cart_order_items",
                    queryset=OrderItem.objects.select_related(
                        "product", "variant", "vendor"
                    ),
                ),
                "order_status_history",
                "payment_records",
                "commercial_transition_logs",
            )
            .select_related("vendor", "delivery_courier")
            .get(id=order_id, user_id=user_id)
        )
    except Order.DoesNotExist:
        return None


def get_order_by_id_for_vendor(order_id, vendor_id) -> Optional[Order]:
    """
    Return a single order for a vendor with full detail prefetched.

    Args:
        order_id: PK of the Order.
        vendor_id: PK of VendorProfile (ownership guard).

    Returns:
        Order instance or None.
    """
    try:
        return (
            Order.objects
            .prefetch_related(
                Prefetch(
                    "cart_order_items",
                    queryset=OrderItem.objects.select_related("product", "variant"),
                ),
                "order_status_history",
                "payment_records",
                "commercial_transition_logs",
            )
            .select_related("user", "delivery_courier")
            .get(id=order_id, vendor_id=vendor_id)
        )
    except Order.DoesNotExist:
        return None


def get_order_by_payment_ref(payment_reference: str) -> Optional[Order]:
    """
    Return an order by Paystack payment reference (used in webhook handler).

    Args:
        payment_reference: Unique Paystack transaction reference string.

    Returns:
        Order instance or None.
    """
    try:
        return Order.objects.get(payment_reference=payment_reference)
    except Order.DoesNotExist:
        return None


def get_admin_orders(
    status: str | None = None,
    user_id=None,
    vendor_id: int | None = None,
):
    """
    Return filtered order list for admin/support views.

    Args:
        status: Optional OrderStatus filter.
        user_id: Optional user PK filter.
        vendor_id: Optional VendorProfile PK filter.

    Returns:
        QuerySet[Order] with user + vendor + items prefetched.
    """
    qs = (
        Order.objects
        .prefetch_related(
            Prefetch(
                "cart_order_items",
                queryset=OrderItem.objects.select_related("product", "variant"),
            ),
        )
        .select_related("user", "vendor", "delivery_courier")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if user_id:
        qs = qs.filter(user_id=user_id)
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    return qs


def get_order_status_counts_for_user(user_id) -> dict[str, int]:
    """
    Return per-status order counts for a client user (used in badge rendering).

    Args:
        user_id: PK of authenticated user.

    Returns:
        dict mapping status string → count integer.
    """
    return Order.get_status_counts_for_user(user_id)


def get_order_status_counts_for_vendor(vendor_id) -> dict[str, int]:
    """
    Return per-status order counts for a vendor (used in vendor dashboard badges).

    Args:
        vendor_id: PK of VendorProfile.

    Returns:
        dict mapping status string → count integer.
    """
    return Order.get_status_counts_for_vendor(vendor_id)


# ══════════════════════════════════════════════════════════════════════
#  ASYNC selectors  (Django-Ninja async router)
#  ── Only Django 6.0 native async ORM — ZERO sync_to_async ──
# ══════════════════════════════════════════════════════════════════════


async def aget_user_orders(
    user_id,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Async: return client order list as list[dict] for Ninja serialization.

    Traversal path:
        user.user_orders → Order rows for this user
        order.order_items → OrderItem rows (via Prefetch)

    Uses async iteration over the QuerySet — zero sync_to_async.

    Args:
        user_id: PK of the authenticated UnifiedUser.
        status: Optional OrderStatus filter string.
        limit: Optional max number of rows to return.

    Returns:
        list[dict] with order summary fields.
    """
    try:
        qs = (
            Order.objects.filter(user_id=user_id)
            .select_related("vendor", "delivery_courier")
            .order_by("-created_at")
            .values(
                "id",
                "order_number",
                "status",
                "total_amount",
                "subtotal",
                "currency",
                "created_at",
                "fulfillment_type",
                "vendor__store_name",
            )
        )
        if status:
            qs = qs.filter(status=status)
        if limit:
            qs = qs[:limit]
        rows = [row async for row in qs]
        return [_normalize_order_list_row(row) for row in rows]
    except Exception as exc:
        logger.error("aget_user_orders user_id=%s: %s", user_id, exc)
        return []


async def aget_order_detail_for_user(
    order_id,
    user_id,
) -> Optional[Order]:
    """
    Async: return a single order for a client user with full prefetch.

    Uses aget() for the ownership-guarded lookup, then
    aprefetch_related_objects() for the async prefetch of items and history.

    Args:
        order_id: PK of the Order.
        user_id: PK of the authenticated user (ownership guard).

    Returns:
        Order instance with order_items and order_status_history prefetched,
        or None if the order does not exist or is not owned by this user.
    """
    try:
        order = await (
            Order.objects
            .select_related("vendor", "delivery_courier", "user")
            .aget(id=order_id, user_id=user_id)
        )
        await aprefetch_related_objects(
            [order],
            Prefetch(
                "cart_order_items",
                queryset=OrderItem.objects.select_related(
                    "product", "variant", "vendor"
                ),
            ),
            "order_status_history",
            "payment_records",
            "commercial_transition_logs",
        )
        return order
    except Order.DoesNotExist:
        return None
    except Exception as exc:
        logger.error(
            "aget_order_detail_for_user order_id=%s user_id=%s: %s",
            order_id, user_id, exc,
        )
        return None


async def aget_order_detail_for_vendor(
    order_id,
    vendor_id,
) -> Optional[Order]:
    """
    Async: return a single order for a vendor with full prefetch.

    Args:
        order_id: PK of the Order.
        vendor_id: PK of VendorProfile (ownership guard).

    Returns:
        Order instance with items and status history prefetched, or None.
    """
    try:
        order = await (
            Order.objects
            .select_related("user", "delivery_courier")
            .aget(id=order_id, vendor_id=vendor_id)
        )
        await aprefetch_related_objects(
            [order],
            Prefetch(
                "cart_order_items",
                queryset=OrderItem.objects.select_related("product", "variant"),
            ),
            "order_status_history",
            "payment_records",
            "commercial_transition_logs",
        )
        return order
    except Order.DoesNotExist:
        return None
    except Exception as exc:
        logger.error(
            "aget_order_detail_for_vendor order_id=%s vendor_id=%s: %s",
            order_id, vendor_id, exc,
        )
        return None


async def aget_order_detail_for_admin(order_id) -> Optional[Order]:
    """Async: return a fully prefetched order for staff/admin review.

    Args:
        order_id: PK of the Order.

    Returns:
        Order instance with user, vendor, items, and status history prefetched,
        or None when the order does not exist.
    """
    try:
        order = await (
            Order.objects
            .select_related("user", "vendor", "delivery_courier")
            .aget(id=order_id)
        )
        await aprefetch_related_objects(
            [order],
            Prefetch(
                "cart_order_items",
                queryset=OrderItem.objects.select_related("product", "variant", "vendor"),
            ),
            "order_status_history",
            "payment_records",
            "commercial_transition_logs",
        )
        return order
    except Order.DoesNotExist:
        return None
    except Exception as exc:
        logger.error("aget_order_detail_for_admin order_id=%s: %s", order_id, exc)
        return None


async def aget_vendor_orders_list(
    vendor_id,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Async: return a vendor's order list as list[dict] for Ninja serialization.

    Traversal path: vendor.vendor_orders → Order rows.
    Uses async iteration — zero sync_to_async.

    Args:
        vendor_id: PK of VendorProfile.
        status: Optional OrderStatus filter.
        limit: Max number of rows (default 50).

    Returns:
        list[dict] with order summary fields for the vendor dashboard.
    """
    try:
        qs = (
            Order.objects.filter(vendor_id=vendor_id)
            .select_related("user")
            .order_by("-created_at")
            .values(
                "id",
                "order_number",
                "status",
                "total_amount",
                "subtotal",
                "commission_amount",
                "vendor_payout",
                "currency",
                "created_at",
                "fulfillment_type",
                "user__email",
            )
        )
        if status:
            qs = qs.filter(status=status)
        rows = [row async for row in qs[:limit]]
        return [_normalize_order_list_row(row) for row in rows]
    except Exception as exc:
        logger.error("aget_vendor_orders_list vendor_id=%s: %s", vendor_id, exc)
        return []


async def aget_admin_orders_list(
    status: str | None = None,
    user_id=None,
    vendor_id=None,
    limit: int = 100,
) -> list[dict]:
    """
    Async: return a filtered order list for admin/support Ninja reads.

    Args:
        status: Optional OrderStatus filter.
        user_id: Optional user PK filter.
        vendor_id: Optional VendorProfile PK filter.
        limit: Max rows returned (default 100).

    Returns:
        list[dict] with order + actor fields.
    """
    try:
        qs = (
            Order.objects.order_by("-created_at")
            .values(
                "id",
                "order_number",
                "status",
                "total_amount",
                "subtotal",
                "currency",
                "created_at",
                "user__email",
                "vendor__store_name",
                "payment_reference",
            )
        )
        if status:
            qs = qs.filter(status=status)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if vendor_id:
            qs = qs.filter(vendor_id=vendor_id)
        rows = [row async for row in qs[:limit]]
        return [_normalize_order_list_row(row) for row in rows]
    except Exception as exc:
        logger.error("aget_admin_orders_list: %s", exc)
        return []


async def aget_order_by_payment_ref(payment_reference: str) -> Optional[Order]:
    """
    Async: return an order by Paystack payment reference for webhook processing.

    This is an async variant of the sync selector used in webhook handlers
    that run inside async Ninja views.

    Args:
        payment_reference: Unique Paystack transaction reference string.

    Returns:
        Order instance or None.
    """
    try:
        return await Order.objects.aget(payment_reference=payment_reference)
    except Order.DoesNotExist:
        return None
    except Exception as exc:
        logger.error("aget_order_by_payment_ref ref=%s: %s", payment_reference, exc)
        return None


async def aget_order_status_counts_for_user(user_id) -> dict[str, int]:
    """
    Async: return per-status order counts for a client user.

    Used for navigation badge rendering (pending orders, active deliveries).
    Uses async iteration over .values().annotate() — no sync_to_async.

    Args:
        user_id: PK of the authenticated user.

    Returns:
        dict mapping status string → count integer, e.g.:
        {"pending_payment": 2, "delivered": 5, "completed": 12}
    """
    try:
        return await Order.aget_status_counts_for_user(user_id)
    except Exception as exc:
        logger.error("aget_order_status_counts_for_user user_id=%s: %s", user_id, exc)
        return {}


async def aget_order_status_counts_for_vendor(vendor_id) -> dict[str, int]:
    """
    Async: return per-status order counts for a vendor.

    Used for vendor dashboard badge rendering and analytics widgets.
    Traversal: vendor.vendor_orders → grouped by status.

    Args:
        vendor_id: PK of VendorProfile.

    Returns:
        dict mapping status string → count integer.
    """
    try:
        return await Order.aget_status_counts_for_vendor(vendor_id)
    except Exception as exc:
        logger.error(
            "aget_order_status_counts_for_vendor vendor_id=%s: %s", vendor_id, exc
        )
        return {}


async def aget_order_financial_summary_for_vendor(vendor_id) -> dict[str, Any]:
    """
    Async: return aggregated financial summary for a vendor.

    Uses aaggregate() for a single-query SUM across paid orders.
    Traversal: vendor.vendor_orders (paid) → sum totals.

    Args:
        vendor_id: PK of VendorProfile.

    Returns:
        dict with keys: total_revenue, total_commission, total_payout, order_count.
    """
    try:
        result = await Order.aget_financial_summary_for_vendor(vendor_id)
        return {
            "total_revenue": float(result["total_revenue"]),
            "total_commission": float(result["total_commission"]),
            "total_payout": float(result["total_payout"]),
            "order_count": result["order_count"],
        }
    except Exception as exc:
        logger.error(
            "aget_order_financial_summary_for_vendor vendor_id=%s: %s", vendor_id, exc
        )
        return {
            "total_revenue": 0.0,
            "total_commission": 0.0,
            "total_payout": 0.0,
            "order_count": 0,
        }
