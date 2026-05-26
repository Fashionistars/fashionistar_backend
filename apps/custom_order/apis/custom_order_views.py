# apps/order/apis/async_/custom_order_views.py
"""
Custom Order API — Django-Ninja Async Router.

Mounted at:
  /api/v1/ninja/client/custom-orders/   → client-facing endpoints
  /api/v1/ninja/vendor/custom-orders/   → vendor-facing endpoints

Authentication: JWT Bearer.

Flow:
  1. Client POST /client/custom-orders/      → create (status=submitted)
  2. GET  /client/custom-orders/             → list client's commissions
  3. GET  /client/custom-orders/{id}/        → detail
  4. Vendor GET  /vendor/custom-orders/      → pending approvals list
  5. Vendor POST /vendor/custom-orders/{id}/approve/   → approve + set amount
  6. Client POST /client/custom-orders/{id}/pay-milestone/ → pay next tranche
"""
from __future__ import annotations

import logging
from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.client.types.client_schemas import (
    CustomOrderApproveIn,
    CustomOrderIn,
    CustomOrderOut,
    MilestonePayIn,
)
from apps.common.roles import is_client_role, is_vendor_role

logger = logging.getLogger(__name__)

client_custom_order_router = Router(tags=["Custom Orders — Client"])
vendor_custom_order_router = Router(tags=["Custom Orders — Vendor"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_client(request):
    user = request.auth
    if user is None or not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access required.")
    return user


def _require_vendor(request):
    user = request.auth
    if user is None or not is_vendor_role(getattr(user, "role", None)):
        raise HttpError(403, "Vendor access required.")
    return user


def _serialize_custom_order(co) -> dict:
    """Serialize a CustomOrder ORM instance to a dict matching CustomOrderOut."""
    milestones = [
        {
            "id": str(m.id),
            "milestone_pct": m.milestone_pct,
            "amount_ngn": m.amount_ngn,
            "payment_status": m.payment_status,
            "paid_at": m.paid_at,
        }
        for m in co.milestones.all()
    ]
    return {
        "id": str(co.id),
        "reference": co.reference,
        "status": co.status,
        "design_brief": co.design_brief,
        "vendor_approval_note": co.vendor_approval_note,
        "budget_ngn": co.budget_ngn,
        "product_snapshot_id": co.product_snapshot_id or None,
        "order_snapshot_id": co.order_snapshot_id or None,
        "vendor_store_name": getattr(
            getattr(co.vendor, "vendor_profile", None), "store_name", ""
        ) or str(co.vendor_id),
        "created_at": co.created_at,
        "updated_at": co.updated_at,
        "milestones": milestones,
    }


# ── Client Endpoints ──────────────────────────────────────────────────────────


@client_custom_order_router.post("/", response={201: CustomOrderOut})
async def create_custom_order(request, payload: CustomOrderIn):
    """
    POST /api/v1/ninja/client/custom-orders/
    Create a new bespoke order commission and submit it to the vendor.
    """
    from apps.order.models import CustomOrder, CustomOrderStatus

    user = _require_client(request)
    try:
        from apps.authentication.models import UnifiedUser
        vendor = await UnifiedUser.objects.aget(pk=payload.vendor_id, role="vendor")
    except Exception:
        raise HttpError(404, "Vendor not found.")

    co = await CustomOrder.objects.acreate(
        client=user,
        vendor=vendor,
        design_brief=payload.design_brief,
        budget_ngn=payload.budget_ngn,
        product_snapshot_id=payload.product_snapshot_id or "",
        order_snapshot_id=payload.order_snapshot_id or "",
        reference_images=payload.reference_images,
        status=CustomOrderStatus.SUBMITTED,
    )
    logger.info("CustomOrder %s created by client %s", co.reference, user.pk)
    return 201, _serialize_custom_order(co)


@client_custom_order_router.get("/", response=list[CustomOrderOut])
async def list_client_custom_orders(request, status: str | None = None):
    """
    GET /api/v1/ninja/client/custom-orders/
    List all custom orders for the authenticated client.
    """
    from apps.order.models import CustomOrder

    user = _require_client(request)
    qs = (
        CustomOrder.objects.filter(client=user, is_deleted=False)
        .select_related("vendor")
        .prefetch_related("milestones")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return [_serialize_custom_order(co) async for co in qs]


@client_custom_order_router.get("/{custom_order_id}/", response=CustomOrderOut)
async def get_client_custom_order(request, custom_order_id: UUID):
    """
    GET /api/v1/ninja/client/custom-orders/{id}/
    Retrieve a single custom order with full milestone detail.
    """
    from apps.order.models import CustomOrder

    user = _require_client(request)
    try:
        co = await (
            CustomOrder.objects
            .filter(id=custom_order_id, client=user, is_deleted=False)
            .select_related("vendor")
            .prefetch_related("milestones")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")
    return _serialize_custom_order(co)


@client_custom_order_router.post("/{custom_order_id}/pay-milestone/", response=CustomOrderOut)
async def pay_next_milestone(request, custom_order_id: UUID, payload: MilestonePayIn):
    """
    POST /api/v1/ninja/client/custom-orders/{id}/pay-milestone/
    Pay the next pending milestone for this custom order.
    Supports wallet, card, and bank_transfer payment methods.
    """
    from django.utils import timezone

    from apps.order.models import CustomOrder, CustomOrderStatus, MilestonePaymentStatus

    user = _require_client(request)
    try:
        co = await (
            CustomOrder.objects
            .filter(id=custom_order_id, client=user, is_deleted=False)
            .prefetch_related("milestones")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")

    if co.status not in (CustomOrderStatus.APPROVED, CustomOrderStatus.IN_PRODUCTION):
        raise HttpError(400, "Order must be approved before milestone payments.")

    # Get next pending milestone
    milestone = await co.milestones.filter(
        payment_status=MilestonePaymentStatus.PENDING,
        milestone_pct=payload.milestone_pct,
    ).afirst()

    if milestone is None:
        raise HttpError(400, f"No pending milestone at {payload.milestone_pct}%.")

    # Mark as paid (payment gateway integration hook goes here)
    milestone.payment_status = MilestonePaymentStatus.PAID
    milestone.paid_at = timezone.now()
    await milestone.asave(update_fields=["payment_status", "paid_at", "updated_at"])

    # Check if all milestones paid → move to in_production
    all_paid = await co.milestones.filter(
        payment_status=MilestonePaymentStatus.PENDING
    ).acount() == 0
    if all_paid:
        co.status = CustomOrderStatus.IN_PRODUCTION
        await co.asave(update_fields=["status", "updated_at"])

    # Refresh with prefetch
    co = await (
        CustomOrder.objects
        .filter(id=custom_order_id)
        .select_related("vendor")
        .prefetch_related("milestones")
        .aget()
    )
    return _serialize_custom_order(co)


# ── Vendor Endpoints ──────────────────────────────────────────────────────────


@vendor_custom_order_router.get("/", response=list[CustomOrderOut])
async def list_vendor_custom_orders(request, status: str | None = None):
    """
    GET /api/v1/ninja/vendor/custom-orders/
    List all bespoke commissions assigned to this vendor.
    """
    from apps.order.models import CustomOrder

    user = _require_vendor(request)
    qs = (
        CustomOrder.objects.filter(vendor=user, is_deleted=False)
        .select_related("client")
        .prefetch_related("milestones")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return [_serialize_custom_order(co) async for co in qs]


@vendor_custom_order_router.post("/{custom_order_id}/approve/", response=CustomOrderOut)
async def approve_custom_order(
    request, custom_order_id: UUID, payload: CustomOrderApproveIn
):
    """
    POST /api/v1/ninja/vendor/custom-orders/{id}/approve/
    Vendor approves the design brief, sets agreed amount, and creates milestones.
    """
    from apps.order.models import CustomOrder, CustomOrderStatus

    user = _require_vendor(request)
    try:
        co = await (
            CustomOrder.objects
            .filter(id=custom_order_id, vendor=user, is_deleted=False)
            .select_related("client")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")

    if co.status != CustomOrderStatus.SUBMITTED:
        raise HttpError(400, "Only submitted orders can be approved.")

    co.status = CustomOrderStatus.APPROVED
    co.vendor_approval_note = payload.vendor_approval_note
    co.agreed_amount_ngn = payload.agreed_amount_ngn
    await co.asave(
        update_fields=["status", "vendor_approval_note", "agreed_amount_ngn", "updated_at"]
    )

    # Create the 4 milestone tranches (30/50/70/100 %)
    # Sync call in async context — wrapped for safety
    from asgiref.sync import sync_to_async
    await sync_to_async(co.create_milestones)()

    logger.info(
        "CustomOrder %s approved by vendor %s. Agreed: %s NGN",
        co.reference, user.pk, co.agreed_amount_ngn,
    )

    # Reload with milestones
    co = await (
        CustomOrder.objects
        .filter(id=custom_order_id)
        .select_related("vendor")
        .prefetch_related("milestones")
        .aget()
    )
    return _serialize_custom_order(co)
