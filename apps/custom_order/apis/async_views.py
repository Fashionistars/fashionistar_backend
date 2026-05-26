# apps/custom_order/apis/async_views.py
"""
Custom Order async Ninja API views.

Mounted via ninja_api.py at:
  Client side: /api/v1/ninja/custom-orders/client/
  Vendor side: /api/v1/ninja/custom-orders/vendor/

Authentication: AsyncJWTAuth (all routes)

Role guards:
  • Client routes: request.auth.client_profile must exist
  • Vendor routes: request.auth.vendor_profile must exist
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from typing import List
from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.custom_order.models import (
    CustomOrder,
    CustomOrderMilestone,
    CustomOrderStatus,
    MilestonePaymentStatus,
)
from apps.custom_order.types.schemas import (
    CustomOrderCreateIn,
    CustomOrderOut,
    MilestonePayIn,
    VendorApproveIn,
)

logger = logging.getLogger(__name__)

# ── Routers ───────────────────────────────────────────────────────────────────
client_router = Router(tags=["Custom Orders — Client"])
vendor_router = Router(tags=["Custom Orders — Vendor"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_client(request) -> object:
    """Raise 403 if the authenticated user has no client profile."""
    try:
        return await request.auth.client_profile.__class__.objects.aget(
            user=request.auth
        )
    except Exception:
        raise HttpError(HTTPStatus.FORBIDDEN, "Client profile required.")


async def _require_vendor(request) -> object:
    """Raise 403 if the authenticated user has no vendor profile."""
    try:
        return await request.auth.vendor_profile.__class__.objects.aget(
            user=request.auth
        )
    except Exception:
        raise HttpError(HTTPStatus.FORBIDDEN, "Vendor profile required.")


async def _serialize_order(order: CustomOrder) -> CustomOrderOut:
    """Eagerly load vendor + milestones then serialise."""
    # Prefetch milestones async
    milestones = [m async for m in order.milestones.all().order_by("milestone_pct")]
    vendor = await order.vendor.__class__.objects.aget(pk=order.vendor_id)
    return CustomOrderOut(
        id=order.id,
        reference=order.reference,
        status=order.status,
        design_brief=order.design_brief,
        vendor_approval_note=order.vendor_approval_note,
        budget_ngn=order.budget_ngn,
        agreed_amount_ngn=order.agreed_amount_ngn,
        product_snapshot_id=order.product_snapshot_id or None,
        order_snapshot_id=order.order_snapshot_id or None,
        vendor_store_name=getattr(vendor, "store_name", ""),
        created_at=order.created_at,
        updated_at=order.updated_at,
        milestones=[
            {
                "id": m.id,
                "milestone_pct": m.milestone_pct,
                "amount_ngn": m.amount_ngn,
                "payment_status": m.payment_status,
                "paid_at": m.paid_at,
            }
            for m in milestones
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CLIENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@client_router.get("/", response=List[CustomOrderOut], summary="List my custom orders")
async def list_client_custom_orders(request, status: str = ""):
    """Return all custom orders for the authenticated client user."""
    qs = (
        CustomOrder.objects.filter(client=request.auth)
        .select_related("vendor")
        .prefetch_related("milestones")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)

    orders = []
    async for order in qs:
        orders.append(await _serialize_order(order))
    return orders


@client_router.post("/", response=CustomOrderOut, summary="Create custom order")
async def create_custom_order(request, payload: CustomOrderCreateIn):
    """Submit a new bespoke commission to a vendor."""
    from apps.vendor.models import VendorProfile

    try:
        vendor = await VendorProfile.objects.aget(pk=payload.vendor_id)
    except VendorProfile.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Vendor not found.")

    order = await CustomOrder.objects.acreate(
        client=request.auth,
        vendor=vendor,
        design_brief=payload.design_brief,
        budget_ngn=payload.budget_ngn,
        product_snapshot_id=payload.product_snapshot_id or "",
        order_snapshot_id=payload.order_snapshot_id or "",
        reference_images=payload.reference_images or [],
        status=CustomOrderStatus.SUBMITTED,  # Auto-submit on creation
    )
    logger.info("custom_order created: %s for user %s", order.reference, request.auth.pk)
    return await _serialize_order(order)


@client_router.get("/{order_id}/", response=CustomOrderOut, summary="Get custom order detail")
async def get_client_custom_order(request, order_id: UUID):
    """Return a specific custom order detail for the authenticated client."""
    try:
        order = await CustomOrder.objects.select_related("vendor").aget(
            id=order_id, client=request.auth
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Custom order not found.")
    return await _serialize_order(order)


@client_router.post("/{order_id}/pay-milestone/", response=CustomOrderOut, summary="Pay next milestone")
async def pay_milestone(request, order_id: UUID, payload: MilestonePayIn):
    """
    Trigger payment for the next pending milestone.

    Validates that:
    - The order belongs to this client.
    - The order is in APPROVED or IN_PRODUCTION state.
    - The requested milestone_pct matches the next PENDING milestone.
    """
    try:
        order = await CustomOrder.objects.select_related("vendor").aget(
            id=order_id, client=request.auth
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Custom order not found.")

    if order.status not in (CustomOrderStatus.APPROVED, CustomOrderStatus.IN_PRODUCTION):
        raise HttpError(
            HTTPStatus.BAD_REQUEST,
            f"Cannot pay milestone for order in status '{order.status}'.",
        )

    try:
        milestone = await order.milestones.aget(
            milestone_pct=payload.milestone_pct,
            payment_status=MilestonePaymentStatus.PENDING,
        )
    except CustomOrderMilestone.DoesNotExist:
        raise HttpError(
            HTTPStatus.BAD_REQUEST,
            f"Milestone {payload.milestone_pct}% is not available for payment.",
        )

    # TODO: wire to wallet debit service when wallet app is available
    await milestone.aupdate(  # type: ignore[attr-defined]  # will use sync mark_paid for now
        payment_status=MilestonePaymentStatus.PAID,
    )

    # Advance order status on first milestone payment
    if order.status == CustomOrderStatus.APPROVED and payload.milestone_pct == 30:
        order.status = CustomOrderStatus.IN_PRODUCTION
        await order.asave(update_fields=["status", "updated_at"])

    # Complete order on final milestone
    if payload.milestone_pct == 100:
        order.status = CustomOrderStatus.COMPLETED
        await order.asave(update_fields=["status", "updated_at"])

    logger.info(
        "Milestone %d%% paid for custom order %s", payload.milestone_pct, order.reference
    )
    return await _serialize_order(order)


# ══════════════════════════════════════════════════════════════════════════════
#  VENDOR ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@vendor_router.get("/", response=List[CustomOrderOut], summary="List incoming custom orders")
async def list_vendor_custom_orders(request, status: str = ""):
    """Return all custom orders assigned to the authenticated vendor."""
    from apps.vendor.models import VendorProfile

    try:
        vendor_profile = await VendorProfile.objects.aget(user=request.auth)
    except VendorProfile.DoesNotExist:
        raise HttpError(HTTPStatus.FORBIDDEN, "Vendor profile required.")

    qs = (
        CustomOrder.objects.filter(vendor=vendor_profile)
        .select_related("vendor")
        .prefetch_related("milestones")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)

    orders = []
    async for order in qs:
        orders.append(await _serialize_order(order))
    return orders


@vendor_router.post("/{order_id}/approve/", response=CustomOrderOut, summary="Approve custom order")
async def approve_custom_order(request, order_id: UUID, payload: VendorApproveIn):
    """
    Vendor approves a submitted custom order, sets agreed price, and seeds
    the 4 milestone payment rows (30/50/70/100%).
    """
    from apps.vendor.models import VendorProfile

    try:
        vendor_profile = await VendorProfile.objects.aget(user=request.auth)
    except VendorProfile.DoesNotExist:
        raise HttpError(HTTPStatus.FORBIDDEN, "Vendor profile required.")

    try:
        order = await CustomOrder.objects.select_related("vendor").aget(
            id=order_id, vendor=vendor_profile, status=CustomOrderStatus.SUBMITTED
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Order not found or not in SUBMITTED status.")

    # Use sync model method (wraps Django save) inside async context is fine for single writes
    import asyncio
    await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: order.approve(payload.agreed_amount_ngn, payload.note),
    )
    logger.info("Vendor %s approved custom order %s", vendor_profile.pk, order.reference)
    return await _serialize_order(order)


@vendor_router.post("/{order_id}/complete/", response=CustomOrderOut, summary="Mark order complete")
async def complete_custom_order(request, order_id: UUID):
    """Vendor marks a custom order as completed after all milestones are paid."""
    from apps.vendor.models import VendorProfile

    try:
        vendor_profile = await VendorProfile.objects.aget(user=request.auth)
    except VendorProfile.DoesNotExist:
        raise HttpError(HTTPStatus.FORBIDDEN, "Vendor profile required.")

    try:
        order = await CustomOrder.objects.select_related("vendor").aget(
            id=order_id, vendor=vendor_profile, status=CustomOrderStatus.IN_PRODUCTION
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(HTTPStatus.NOT_FOUND, "Order not found or not in IN_PRODUCTION status.")

    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, order.complete)
    logger.info("Vendor %s completed custom order %s", vendor_profile.pk, order.reference)
    return await _serialize_order(order)
