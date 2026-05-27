# apps/admin_backend/dashboard_api.py
"""
Admin Dashboard KPI Aggregator — Django Ninja async router.

Provides a single /api/admin/dashboard/kpi/ endpoint that returns all
dashboard headline metrics in one response, preventing N×round-trips
from the frontend dashboard page.

Each metric anchors on ONE primary model and uses async acount() to
avoid blocking the event loop. This router is mounted centrally in
apps/admin_backend/urls.py.

Performance Contract:
  - All queries are async (Django 6.0 native async ORM)
  - select_related / prefetch_related where traversal is needed
  - No N+1 joins: each counter is a single acount() call
"""

from __future__ import annotations

from django.utils import asyncio

import logging
from typing import Optional

from django.utils import timezone
from ninja import Router
from ninja.security import HttpBearer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = Router(tags=["Admin Dashboard"])


# ─────────────────────────────────────────────────────────────────────────────
# Response Schema
# ─────────────────────────────────────────────────────────────────────────────

class KPICardSchema(BaseModel):
    """Individual KPI metric card."""
    label: str
    value: int
    trend: Optional[float] = None          # % change vs previous period
    unit: Optional[str] = None             # "NGN", "%", etc.


class AdminDashboardKPISchema(BaseModel):
    """Aggregated KPI response for the admin dashboard overview."""
    # Users
    total_users: int
    new_users_today: int
    active_vendors: int
    # Commerce
    total_products: int
    products_pending_review: int
    low_stock_products: int
    # Orders
    total_orders: int
    orders_today: int
    orders_pending: int
    # KYC
    pending_kyc_submissions: int
    # Financial
    total_wallets: int
    # Support
    open_support_tickets: int
    # Timestamp
    generated_at: str


# ─────────────────────────────────────────────────────────────────────────────
# KPI Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/kpi/",
    response=AdminDashboardKPISchema,
    summary="Admin Dashboard KPI Overview",
    description=(
        "Returns all headline KPI metrics for the admin dashboard overview page. "
        "Each metric is fetched independently using Django async ORM acount(). "
        "Required: admin or superuser role."
    ),
    auth=None,  # Auth enforced by URL-level middleware in admin_backend router
)
async def admin_dashboard_kpi(request):
    """
    Aggregate admin KPI metrics asynchronously.

    Each metric is a standalone acount() — no multi-model joins.
    Failures in individual counters are logged and default to 0
    (fail-soft so one broken model doesn't crash the dashboard).
    """
    from apps.authentication.models import UnifiedUser
    from apps.vendor.models import VendorProfile
    from apps.product.models import Product, ProductStatus
    from apps.order.models import Order
    from apps.kyc.models import KYCSubmission
    from apps.wallet.models import Wallet
    from apps.support.models import SupportTicket

    today = timezone.now().date()

    async def safe_count(queryset) -> int:
        """Await acount() with fail-soft — returns 0 on any error."""
        try:
            return await queryset.acount()
        except Exception as exc:
            logger.warning("KPI counter failed: %s", exc)
            return 0

    # ── Users ──────────────────────────────────────────────────────────────
    total_users = await safe_count(
        UnifiedUser.objects.filter(is_deleted=False)
    )
    new_users_today = await safe_count(
        UnifiedUser.objects.filter(
            is_deleted=False,
            date_joined__date=today,
        )
    )

    # ── Vendors ────────────────────────────────────────────────────────────
    # Anchor: VendorProfile — traverse nothing
    active_vendors = await safe_count(
        VendorProfile.objects.filter(
            is_approved=True,
            user__is_active=True,
            user__is_deleted=False,
        ).select_related("user")
    )

    # ── Products ───────────────────────────────────────────────────────────
    total_products = await safe_count(
        Product.objects.filter(is_deleted=False)
    )
    products_pending_review = await safe_count(
        Product.objects.filter(
            status=ProductStatus.PENDING,
            is_deleted=False,
        )
    )
    low_stock_products = await safe_count(
        Product.objects.filter(
            is_deleted=False,
            in_stock=True,
            stock_qty__lte=5,
            stock_qty__gt=0,
        )
    )

    # ── Orders ─────────────────────────────────────────────────────────────
    total_orders = await safe_count(Order.objects.all())
    orders_today = await safe_count(
        Order.objects.filter(created_at__date=today)
    )
    orders_pending = await safe_count(
        Order.objects.filter(
            status__in=["pending", "payment_pending", "processing"]
        )
    )

    # ── KYC ────────────────────────────────────────────────────────────────
    pending_kyc_submissions = await safe_count(
        KYCSubmission.objects.filter(status="pending")
    )

    # ── Wallets ────────────────────────────────────────────────────────────
    total_wallets = await safe_count(Wallet.objects.all())

    # ── Support ────────────────────────────────────────────────────────────
    open_support_tickets = await safe_count(
        SupportTicket.objects.filter(status__in=["open", "in_progress"])
    )
    asyncio.gather(
        total_users,
        new_users_today,
        active_vendors,
        total_products,
        products_pending_review,
        low_stock_products,
        total_orders,
        orders_today,
        orders_pending,
        pending_kyc_submissions,
        total_wallets,
        open_support_tickets,
    )

    return AdminDashboardKPISchema(
        total_users=total_users,
        new_users_today=new_users_today,
        active_vendors=active_vendors,
        total_products=total_products,
        products_pending_review=products_pending_review,
        low_stock_products=low_stock_products,
        total_orders=total_orders,
        orders_today=orders_today,
        orders_pending=orders_pending,
        pending_kyc_submissions=pending_kyc_submissions,
        total_wallets=total_wallets,
        open_support_tickets=open_support_tickets,
        generated_at=timezone.now().isoformat(),
    )
