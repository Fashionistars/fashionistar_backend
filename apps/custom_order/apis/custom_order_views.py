# apps/custom_order/apis/custom_order_views.py
"""
Custom Order (Bespoke Commission) API — Django-Ninja Async Router.

Mounted in backend/ninja_api.py at:
  /api/v1/ninja/client/custom-orders/   → client_custom_order_router
  /api/v1/ninja/vendor/custom-orders/   → vendor_custom_order_router

Authentication: AsyncJWTAuth (all routes inherit from NinjaAPI auth).

Flow:
  1. Client POST  /client/custom-orders/              → create (status=submitted)
  2. Client GET   /client/custom-orders/              → list client's commissions
  3. Client GET   /client/custom-orders/{id}/         → detail
  4. Client POST  /client/custom-orders/{id}/pay-milestone/ → pay next tranche
  5. Vendor GET   /vendor/custom-orders/              → pending approvals list
  6. Vendor POST  /vendor/custom-orders/{id}/approve/ → approve + set agreed amount + seed milestones
  7. Vendor POST  /vendor/custom-orders/{id}/cancel/  → cancel a submitted order
"""
from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.common.roles import is_client_role, is_vendor_role
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

client_custom_order_router = Router(tags=["Custom Orders — Client"])
vendor_custom_order_router = Router(tags=["Custom Orders — Vendor"])


# ── Role Guards ───────────────────────────────────────────────────────────────

def _require_client(request):
    """Raise 403 if the authenticated user has no client role."""
    user = request.auth
    if user is None or not is_client_role(getattr(user, "role", None)):
        raise HttpError(403, "Client access required.")
    return user


def _require_vendor(request):
    """Raise 403 if the authenticated user has no vendor role."""
    user = request.auth
    if user is None or not is_vendor_role(getattr(user, "role", None)):
        raise HttpError(403, "Vendor access required.")
    return user


# ── Serializer ────────────────────────────────────────────────────────────────

def _serialize_custom_order(co) -> dict:
    """Serialize a CustomOrder ORM instance to a dict matching CustomOrderOut schema."""
    milestones = [
        {
            "id": str(m.id),
            "milestone_pct": m.milestone_pct,
            "amount_ngn": m.amount_ngn,
            "payment_status": m.payment_status,
            "paid_at": m.paid_at,
        }
        for m in co.milestones.all().order_by("milestone_pct")
    ]
    # CustomOrder.vendor FK → VendorProfile
    vendor_obj = getattr(co, "vendor", None)
    vendor_store_name = (
        getattr(vendor_obj, "store_name", None) or str(getattr(vendor_obj, "id", ""))
    )
    return {
        "id": str(co.id),
        "reference": co.reference,
        "status": co.status,
        "design_brief": co.design_brief,
        "vendor_approval_note": co.vendor_approval_note or "",
        "budget_ngn": co.budget_ngn,
        "agreed_amount_ngn": co.agreed_amount_ngn,
        "product_snapshot_id": co.product_snapshot_id or None,
        "order_snapshot_id": co.order_snapshot_id or None,
        "vendor_store_name": vendor_store_name,
        "created_at": co.created_at,
        "updated_at": co.updated_at,
        "milestones": milestones,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLIENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════


@client_custom_order_router.post("/", response={201: CustomOrderOut})
async def create_custom_order(request, payload: CustomOrderCreateIn):
    """
    POST /api/v1/ninja/client/custom-orders/
    Create a new bespoke order commission and submit it immediately to the vendor.
    """
    from apps.vendor.models import VendorProfile

    user = _require_client(request)
    try:
        vendor = await VendorProfile.objects.aget(pk=payload.vendor_id)
    except VendorProfile.DoesNotExist:
        raise HttpError(404, "Vendor not found.")

    co = await CustomOrder.objects.acreate(
        client=user,
        vendor=vendor,
        design_brief=payload.design_brief,
        budget_ngn=payload.budget_ngn,
        product_snapshot_id=payload.product_snapshot_id or "",
        order_snapshot_id=payload.order_snapshot_id or "",
        reference_images=payload.reference_images or [],
        status=CustomOrderStatus.SUBMITTED,
    )
    logger.info("CustomOrder %s created by client %s", co.reference, user.pk)
    return 201, _serialize_custom_order(co)


@client_custom_order_router.get("/", response=List[CustomOrderOut])
async def list_client_custom_orders(request, status: str | None = None):
    """
    GET /api/v1/ninja/client/custom-orders/
    List all custom orders for the authenticated client.
    """
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
    user = _require_client(request)
    try:
        co = await (
            CustomOrder.objects.filter(
                id=custom_order_id, client=user, is_deleted=False
            )
            .select_related("vendor")
            .prefetch_related("milestones")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")
    return _serialize_custom_order(co)


@client_custom_order_router.post(
    "/{custom_order_id}/pay-milestone/", response=CustomOrderOut
)
async def pay_next_milestone(
    request, custom_order_id: UUID, payload: MilestonePayIn
):
    """
    POST /api/v1/ninja/client/custom-orders/{id}/pay-milestone/
    Pay the next pending milestone for this custom order.

    Validates:
    - Order belongs to this client.
    - Order is APPROVED or IN_PRODUCTION.
    - Requested milestone_pct has a PENDING row.

    Payment gateway hook: currently marks milestone PAID directly.
    Wire to WalletDebitService / PaystackService in billing sprint.
    """
    user = _require_client(request)
    try:
        co = await (
            CustomOrder.objects.filter(
                id=custom_order_id, client=user, is_deleted=False
            )
            .prefetch_related("milestones")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")

    if co.status not in (CustomOrderStatus.APPROVED, CustomOrderStatus.IN_PRODUCTION):
        raise HttpError(400, "Order must be approved before milestone payments.")

    # Locate the pending milestone
    milestone = await co.milestones.filter(
        payment_status=MilestonePaymentStatus.PENDING,
        milestone_pct=payload.milestone_pct,
    ).afirst()

    if milestone is None:
        raise HttpError(400, f"No pending milestone at {payload.milestone_pct}%.")

    # Mark paid (payment gateway integration hook)
    milestone.payment_status = MilestonePaymentStatus.PAID
    milestone.paid_at = timezone.now()
    await milestone.asave(update_fields=["payment_status", "paid_at", "updated_at"])

    # Transition: first payment → in_production
    if co.status == CustomOrderStatus.APPROVED and payload.milestone_pct == 30:
        co.status = CustomOrderStatus.IN_PRODUCTION
        await co.asave(update_fields=["status", "updated_at"])

    # Transition: all milestones paid → check for completion
    pending_remaining = await co.milestones.filter(
        payment_status=MilestonePaymentStatus.PENDING
    ).acount()
    if pending_remaining == 0:
        co.status = CustomOrderStatus.IN_PRODUCTION
        await co.asave(update_fields=["status", "updated_at"])

    logger.info(
        "Milestone %d%% paid for custom order %s by client %s",
        payload.milestone_pct,
        co.reference,
        user.pk,
    )

    # Reload with select_related + prefetch for serialization
    co = await (
        CustomOrder.objects.filter(id=custom_order_id)
        .select_related("vendor")
        .prefetch_related("milestones")
        .aget()
    )
    return _serialize_custom_order(co)


# ══════════════════════════════════════════════════════════════════════════════
#  VENDOR ROUTES
# ══════════════════════════════════════════════════════════════════════════════


@vendor_custom_order_router.get("/", response=List[CustomOrderOut])
async def list_vendor_custom_orders(request, status: str | None = None):
    """
    GET /api/v1/ninja/vendor/custom-orders/
    List all bespoke commissions assigned to this vendor.
    """
    from apps.vendor.models import VendorProfile

    user = _require_vendor(request)
    try:
        vendor_profile = await VendorProfile.objects.aget(user=user)
    except VendorProfile.DoesNotExist:
        raise HttpError(403, "Vendor profile required.")

    qs = (
        CustomOrder.objects.filter(vendor=vendor_profile, is_deleted=False)
        .select_related("vendor", "client")
        .prefetch_related("milestones")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return [_serialize_custom_order(co) async for co in qs]


@vendor_custom_order_router.post(
    "/{custom_order_id}/approve/", response=CustomOrderOut
)
async def approve_custom_order(
    request, custom_order_id: UUID, payload: VendorApproveIn
):
    """
    POST /api/v1/ninja/vendor/custom-orders/{id}/approve/
    Vendor approves the design brief, sets agreed amount, and seeds milestone rows.
    """
    from apps.vendor.models import VendorProfile

    user = _require_vendor(request)
    try:
        vendor_profile = await VendorProfile.objects.aget(user=user)
    except VendorProfile.DoesNotExist:
        raise HttpError(403, "Vendor profile required.")

    try:
        co = await (
            CustomOrder.objects.filter(
                id=custom_order_id, vendor=vendor_profile, is_deleted=False
            )
            .select_related("client", "vendor")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")

    if co.status != CustomOrderStatus.SUBMITTED:
        raise HttpError(400, "Only submitted orders can be approved.")

    # Persist approval
    co.status = CustomOrderStatus.APPROVED
    co.vendor_approval_note = payload.note or ""
    co.agreed_amount_ngn = payload.agreed_amount_ngn
    await co.asave(
        update_fields=["status", "vendor_approval_note", "agreed_amount_ngn", "updated_at"]
    )

    # Seed the 4 milestone tranches (30/50/70/100%)
    from asgiref.sync import sync_to_async
    await sync_to_async(co.create_milestones)()

    logger.info(
        "CustomOrder %s approved by vendor %s. Agreed: %s NGN",
        co.reference,
        user.pk,
        co.agreed_amount_ngn,
    )

    # Reload with milestones
    co = await (
        CustomOrder.objects.filter(id=custom_order_id)
        .select_related("vendor")
        .prefetch_related("milestones")
        .aget()
    )
    return _serialize_custom_order(co)


@vendor_custom_order_router.post(
    "/{custom_order_id}/cancel/", response=CustomOrderOut
)
async def cancel_custom_order(request, custom_order_id: UUID):
    """
    POST /api/v1/ninja/vendor/custom-orders/{id}/cancel/
    Vendor cancels a submitted (pre-approval) custom order.
    """
    from apps.vendor.models import VendorProfile

    user = _require_vendor(request)
    try:
        vendor_profile = await VendorProfile.objects.aget(user=user)
    except VendorProfile.DoesNotExist:
        raise HttpError(403, "Vendor profile required.")

    try:
        co = await (
            CustomOrder.objects.filter(
                id=custom_order_id, vendor=vendor_profile, is_deleted=False
            )
            .select_related("vendor")
            .aget()
        )
    except CustomOrder.DoesNotExist:
        raise HttpError(404, "Custom order not found.")

    if co.status not in (CustomOrderStatus.SUBMITTED, CustomOrderStatus.DRAFT):
        raise HttpError(400, "Only submitted or draft orders can be cancelled.")

    co.status = CustomOrderStatus.CANCELLED
    await co.asave(update_fields=["status", "updated_at"])
    logger.info("CustomOrder %s cancelled by vendor %s", co.reference, user.pk)

    return _serialize_custom_order(co)
