# apps/order/apis/async_/order_views.py
"""
Order Domain — Django-Ninja Async Read Router.

Mounted at: /api/v1/ninja/orders/

Authentication: JWT Bearer (AsyncJWTAuth from backend.ninja_api).
               request.auth is the authenticated UnifiedUser instance.

Architecture Contract (NON-NEGOTIABLE):
  ─ READ-ONLY — zero writes in this router.
  ─ Mutation endpoints live on DRF sync surface at /api/v1/orders/*.
  ─ All reads delegate to selectors ONLY (apps.order.selectors).
  ─ ZERO direct ORM calls inside this file.
  ─ ZERO sync_to_async usage.

All handler functions are `async def`.
Response serialization uses inline dicts (JSON-safe).
"""

import logging

from ninja import Router
from ninja.errors import HttpError

from apps.order.selectors.order_selectors import (
    aget_order_detail_for_admin,
    aget_order_detail_for_user,
    aget_order_detail_for_vendor,
    aget_order_financial_summary_for_vendor,
    aget_order_status_counts_for_user,
    aget_order_status_counts_for_vendor,
    aget_admin_orders_list,
    aget_user_orders,
    aget_vendor_orders_list,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Order — Async Reads"])


# ── Helpers ─────────────────────────────────────────────────────────────────


def _get_user(request):
    """Return authenticated user from Ninja JWT Bearer auth."""
    user = request.auth.user if hasattr(request.auth, "user") else request.auth
    if user is None:
        raise HttpError(401, "Authentication required.")
    return user


def _require_client_user(request):
    """Return user or raise 403 if role is not 'client'."""
    user = _get_user(request)
    role = getattr(user, "role", None)
    if role not in ("client", "admin"):
        raise HttpError(403, "Client access is required for this endpoint.")
    return user


def _require_vendor_user(request):
    """Return user or raise 403 if role is not 'vendor'."""
    user = _get_user(request)
    role = getattr(user, "role", None)
    if role not in ("vendor", "admin"):
        raise HttpError(403, "Vendor access is required for this endpoint.")
    return user


def _require_admin_user(request):
    """Return user or raise 403 if not admin."""
    user = _get_user(request)
    if not getattr(user, "is_staff", False):
        raise HttpError(403, "Admin access is required for this endpoint.")
    return user


def _serialize_order(order) -> dict:
    """Convert an Order instance to a JSON-safe dict for Ninja response."""
    payment_status = (
        "paid"
        if order.status
        in {"payment_confirmed", "processing", "shipped", "delivered", "completed"}
        else "unpaid"
    )
    return {
        "id": order.pk,
        "order_number": order.order_number,
        "status": order.status,
        "payment_status": payment_status,
        "escrow_status": "released" if order.status == "completed" else "held",
        "fulfillment_type": order.fulfillment_type,
        "total_amount": str(order.total_amount),
        "subtotal": str(order.subtotal),
        "final_total": str(order.total_amount),
        "shipping_amount": str(order.shipping_amount),
        "discount_amount": str(order.discount_amount),
        "commission_amount": str(order.commission_amount),
        "vendor_payout": str(order.vendor_payout),
        "currency": order.currency,
        "requires_measurement": bool(order.measurement_profile_id),
        "payment_reference": order.payment_reference,
        "payment_gateway": order.payment_gateway,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "tracking_number": order.tracking_number,
        "estimated_delivery": (
            order.estimated_delivery.isoformat() if order.estimated_delivery else None
        ),
        "coupon_code": order.coupon_code,
        "delivery_address": order.delivery_address,
        "is_custom_order": order.is_custom_order,
        "notes": order.notes,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "item_count": len(_serialize_order_items(order)),
        "buyer_name": "",
        "buyer_email": getattr(order.user, "email", "") if order.user_id else "",
        "buyer_phone": None,
        "buyer_address": order.delivery_address or {},
        "idempotency_key": order.idempotency_key,
        "delivery_tracking": None,
        "refund_request": None,
        "vendor": (
            {"id": order.vendor_id, "store_name": order.vendor.store_name}
            if order.vendor_id and hasattr(order, "vendor") and order.vendor
            else None
        ),
        "items": _serialize_order_items(order),
        "status_history": _serialize_status_history(order),
    }


def _serialize_order_items(order) -> list[dict]:
    """Serialize prefetched cart_order_items (CartOrderItem) for the order."""
    items = []
    # Support both 'order_items' and 'cart_order_items' prefetch names
    for attr in ("cart_order_items", "order_items"):
        try:
            qs = getattr(order, attr)
            # If it's a RelatedManager, all() was prefetched — iterate cache
            raw = list(qs.all())
            if raw:
                for item in raw:
                    items.append({
                        "id": item.pk,
                        "product_id": str(item.product_id or ""),
                        "product_title": getattr(
                            item, "product_title_snapshot",
                            getattr(item, "product_title", ""),
                        ),
                        "product_sku": getattr(
                            item, "product_sku_snapshot",
                            getattr(item, "sku", ""),
                        ),
                        "variant_description": getattr(
                            item, "variant_description_snapshot",
                            getattr(item, "variant_label", ""),
                        ),
                        "vendor_name": getattr(
                            item, "vendor_name_snapshot",
                            getattr(item, "vendor_name", ""),
                        ),
                        "vendor_id": str(item.vendor_id or ""),
                        "variant_id": str(item.variant_id) if item.variant_id else None,
                        "size_label": getattr(item, "size_snapshot", None) or None,
                        "color_label": getattr(item, "color_snapshot", None) or None,
                        "unit_price": str(item.unit_price),
                        "quantity": item.quantity,
                        "line_total": str(getattr(item, "line_total", item.unit_price * item.quantity)),
                        "commission_rate": str(getattr(item, "commission_rate", "0.00")),
                        "currency_code": getattr(order, "currency", "NGN"),
                        "requires_measurement": bool(getattr(item, "measurement_data", {})),
                    })
                break
        except AttributeError:
            continue
    return items


def _serialize_status_history(order) -> list[dict]:
    """Serialize prefetched order_status_history rows."""
    try:
        return [
            {
                "id": h.pk,
                "from_status": getattr(h, "from_status", None),
                "to_status": h.status if hasattr(h, "status") else getattr(h, "to_status", None),
                "note": getattr(h, "note", ""),
                "created_at": h.created_at.isoformat(),
            }
            for h in order.order_status_history.all()
        ]
    except AttributeError:
        return []


# ══════════════════════════════════════════════════════════════════════
#  CLIENT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/")
async def get_client_order_list(request, status: str = "", limit: int = 20):
    """
    GET /api/v1/ninja/orders/

    Return the authenticated client's order list, most recent first.

    Query params:
        status (optional): Filter by OrderStatus string (e.g. "pending_payment").
        limit (optional): Max rows (default 20, max 100).

    Returns:
        {"status": "success", "count": int, "data": list[dict]}
    """
    user = _require_client_user(request)
    try:
        rows = await aget_user_orders(
            user_id=user.pk,
            status=status or None,
            limit=min(limit, 100),
        )
        return {"status": "success", "count": len(rows), "data": rows}
    except Exception:
        logger.exception("get_client_order_list user=%s", user.pk)
        raise HttpError(500, "Failed to fetch order list.")


@router.get("/counts/")
async def get_client_order_status_counts(request):
    """
    GET /api/v1/ninja/orders/counts/

    Return per-status order counts for the authenticated client.
    Used for navigation badge rendering.

    Returns:
        {"status": "success", "data": {"pending_payment": 2, "completed": 5, ...}}
    """
    user = _require_client_user(request)
    try:
        counts = await aget_order_status_counts_for_user(user_id=user.pk)
        return {"status": "success", "data": counts}
    except Exception:
        logger.exception("get_client_order_status_counts user=%s", user.pk)
        raise HttpError(500, "Failed to fetch order counts.")


@router.get("/admin/")
async def get_admin_order_list(
    request,
    status: str = "",
    user_id: str = "",
    vendor_id: str = "",
    limit: int = 100,
):
    """
    GET /api/v1/ninja/orders/admin/

    Return a staff-only order feed for the admin dashboard.

    Query params:
        status: Optional OrderStatus filter.
        user_id: Optional client user id.
        vendor_id: Optional vendor profile id.
        limit: Max rows, capped at 200.

    Returns:
        {"status": "success", "count": int, "data": list[dict]}
    """
    user = _require_admin_user(request)
    try:
        rows = await aget_admin_orders_list(
            status=status or None,
            user_id=user_id or None,
            vendor_id=vendor_id or None,
            limit=min(limit, 200),
        )
        return {"status": "success", "count": len(rows), "data": rows}
    except Exception:
        logger.exception("get_admin_order_list user=%s", user.pk)
        raise HttpError(500, "Failed to fetch admin order list.")


@router.get("/admin/{order_id}/")
async def get_admin_order_detail(request, order_id: str):
    """Return full order detail for staff/admin review."""
    user = _require_admin_user(request)
    try:
        order = await aget_order_detail_for_admin(order_id=order_id)
        if order is None:
            raise HttpError(404, "Order not found.")
        return {"status": "success", "data": _serialize_order(order)}
    except HttpError:
        raise
    except Exception:
        logger.exception("get_admin_order_detail user=%s order=%s", user.pk, order_id)
        raise HttpError(500, "Failed to fetch admin order detail.")


@router.get("/{order_id}/")
async def get_client_order_detail(request, order_id: str):
    """
    GET /api/v1/ninja/orders/{order_id}/

    Return full order detail for the authenticated client.
    Ownership guarded — returns 404 if the order does not belong to this user.

    Path params:
        order_id: PK of the Order.

    Returns:
        {"status": "success", "data": OrderDetailOut}
    """
    user = _require_client_user(request)
    try:
        order = await aget_order_detail_for_user(order_id=order_id, user_id=user.pk)
        if order is None:
            raise HttpError(404, "Order not found.")
        return {"status": "success", "data": _serialize_order(order)}
    except HttpError:
        raise
    except Exception:
        logger.exception("get_client_order_detail user=%s order=%s", user.pk, order_id)
        raise HttpError(500, "Failed to fetch order detail.")


# ══════════════════════════════════════════════════════════════════════
#  VENDOR ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/vendor/")
async def get_vendor_order_list(request, status: str = "", limit: int = 50):
    """
    GET /api/v1/ninja/orders/vendor/

    Return order list for the authenticated vendor.
    Vendor role required.

    Query params:
        status (optional): Filter by OrderStatus string.
        limit (optional): Max rows (default 50, max 200).

    Returns:
        {"status": "success", "count": int, "data": list[dict]}
    """
    user = _require_vendor_user(request)
    try:
        vendor_profile = getattr(user, "vendor_profile", None)
        if vendor_profile is None:
            raise HttpError(404, "Vendor profile not found. Complete vendor setup first.")
        rows = await aget_vendor_orders_list(
            vendor_id=vendor_profile.pk,
            status=status or None,
            limit=min(limit, 200),
        )
        return {"status": "success", "count": len(rows), "data": rows}
    except HttpError:
        raise
    except Exception:
        logger.exception("get_vendor_order_list user=%s", user.pk)
        raise HttpError(500, "Failed to fetch vendor order list.")


@router.get("/vendor/counts/")
async def get_vendor_order_status_counts(request):
    """
    GET /api/v1/ninja/orders/vendor/counts/

    Return per-status order counts for the authenticated vendor.
    Used for vendor dashboard badge rendering.

    Returns:
        {"status": "success", "data": {"pending_payment": 2, "shipped": 7, ...}}
    """
    user = _require_vendor_user(request)
    try:
        vendor_profile = getattr(user, "vendor_profile", None)
        if vendor_profile is None:
            raise HttpError(404, "Vendor profile not found.")
        counts = await aget_order_status_counts_for_vendor(vendor_id=vendor_profile.pk)
        return {"status": "success", "data": counts}
    except HttpError:
        raise
    except Exception:
        logger.exception("get_vendor_order_status_counts user=%s", user.pk)
        raise HttpError(500, "Failed to fetch vendor order counts.")


@router.get("/vendor/financial-summary/")
async def get_vendor_financial_summary(request):
    """
    GET /api/v1/ninja/orders/vendor/financial-summary/

    Return aggregated financial summary for the authenticated vendor.
    Uses a single aaggregate() query — extremely fast.

    Returns:
        {
          "status": "success",
          "data": {
            "total_revenue": float,
            "total_commission": float,
            "total_payout": float,
            "order_count": int
          }
        }
    """
    user = _require_vendor_user(request)
    try:
        vendor_profile = getattr(user, "vendor_profile", None)
        if vendor_profile is None:
            raise HttpError(404, "Vendor profile not found.")
        summary = await aget_order_financial_summary_for_vendor(vendor_id=vendor_profile.pk)
        return {"status": "success", "data": summary}
    except HttpError:
        raise
    except Exception:
        logger.exception("get_vendor_financial_summary user=%s", user.pk)
        raise HttpError(500, "Failed to fetch financial summary.")


@router.get("/vendor/{order_id}/")
async def get_vendor_order_detail(request, order_id: str):
    """
    GET /api/v1/ninja/orders/vendor/{order_id}/

    Return full order detail for the authenticated vendor.
    Ownership guarded — returns 404 if not owned by this vendor.

    Path params:
        order_id: PK of the Order.

    Returns:
        {"status": "success", "data": OrderDetailOut}
    """
    user = _require_vendor_user(request)
    try:
        vendor_profile = getattr(user, "vendor_profile", None)
        if vendor_profile is None:
            raise HttpError(404, "Vendor profile not found.")
        order = await aget_order_detail_for_vendor(
            order_id=order_id, vendor_id=vendor_profile.pk
        )
        if order is None:
            raise HttpError(404, "Order not found.")
        return {"status": "success", "data": _serialize_order(order)}
    except HttpError:
        raise
    except Exception:
        logger.exception("get_vendor_order_detail user=%s order=%s", user.pk, order_id)
        raise HttpError(500, "Failed to fetch vendor order detail.")
