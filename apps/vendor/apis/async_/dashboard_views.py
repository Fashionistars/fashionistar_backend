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
import asyncio
from uuid import UUID
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, Count, Sum, F, Q
from django.db.models.functions import ExtractMonth, ExtractHour

from ninja import Router
from ninja.errors import HttpError

from apps.vendor.services.vendor_dashboard_service import VendorDashboardService
from apps.vendor.types.vendor_schemas import (
    SetupStateOut,
    VendorDashboardOut,
    VendorProfileOut,
    TopProductOut,
    AnalyticsSummaryOut,
    ChartPointOut,
    ChartResponseOut,
    EarningTrackerOut,
    CustomerBehaviorOut,
    CategoryPerformanceOut,
    PaymentDistributionOut,
    ProductListItemOut,
    OrderListItemOut,
    OrderDetailOut,
    VendorOrderItemOut,
    ReviewListItemOut,
    CouponListItemOut,
    OrderListResponseOut,
    ReviewListResponseOut,
    CouponListResponseOut,
)
from apps.common.roles import is_vendor_role


logger = logging.getLogger(__name__)

router = Router(tags=["Vendor — Async Dashboard"])


def map_order_status(backend_status: str) -> str:
    mapping = {
        "pending_payment": "Pending",
        "awaiting_cash_confirmation": "Pending",
        "processing": "Processing",
        "shipped": "Shipped",
        "out_for_delivery": "Shipped",
        "delivered": "Fulfilled",
        "completed": "Fulfilled",
        "cancelled": "Cancelled",
        "refund_requested": "Cancelled",
        "refunded": "Cancelled",
        "disputed": "Pending",
    }
    return mapping.get(backend_status, "Pending")


def map_payment_status(backend_status: str) -> str:
    if backend_status in {
        "payment_confirmed",
        "processing",
        "shipped",
        "out_for_delivery",
        "delivered",
        "completed",
    }:
        return "paid"
    elif backend_status in {"cancelled", "refunded"}:
        return "failed"
    else:
        return "pending"

def _require_vendor_user(request, require_profile: bool = True):
    """Return the authenticated vendor user or raise a 403 / 404 error."""

    user = request.auth.user if hasattr(request.auth, "user") else request.auth
    if user is None or not is_vendor_role(getattr(user, "role", None)):
        raise HttpError(403, "Vendor access is required for this endpoint.")
    
    if require_profile:
        if getattr(user, "vendor_profile", None) is None:
            raise HttpError(403, "Vendor setup is required before accessing this endpoint.")
            
    return user
            


# ── Dashboard ──────────────────────────────────────────────────────────────


@router.get("/dashboard/", response=VendorDashboardOut)
async def get_vendor_dashboard(request):
    """
    GET /api/v1/ninja/vendor/dashboard/

    Full vendor dashboard: profile, analytics, setup state, recent orders,
    products, reviews, coupons, wallet, recent activity.
    """
    user = _require_vendor_user(request, require_profile=True)
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

    user = _require_vendor_user(request, require_profile=True)
    profile = await aget_vendor_profile_or_none(user)
    if profile is None:
        raise HttpError(404, "Vendor setup is required before profile access.")

    try:
        setup_state = getattr(profile, "vendor_setup_state", None)
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
        logo_url=profile.logo_url.url if getattr(profile.logo_url, "url", None) else (profile.logo_url if isinstance(profile.logo_url, str) and profile.logo_url else ""),
        cover_url=profile.cover_url.url if getattr(profile.cover_url, "url", None) else (profile.cover_url if isinstance(profile.cover_url, str) and profile.cover_url else ""),
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
        subscription_tier=profile.subscription_tier,
        avg_fulfillment_days=profile.avg_fulfillment_days,
        return_rate=profile.return_rate,
        dispute_rate=profile.dispute_rate,
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

    user = _require_vendor_user(request, require_profile=False)
    try:
        profile = await aget_vendor_profile_or_none(user)
        if profile is None:
            return SetupStateOut(
                current_step=1,
                profile_complete=False,
                bank_details=False,
                id_verified=False,
                first_product=False,
                onboarding_done=False,
                completion_percentage=0,
            )
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


# ── Analytics Migrated Endpoints ──────────────────────────────────────────────────

@router.get("/analytics/", response=AnalyticsSummaryOut)
async def get_vendor_analytics_summary(request):
    """
    GET /api/v1/ninja/vendor/analytics/
    Returns full analytics summary KPI data.
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        (
            todays_sales,
            this_month_sales,
            year_to_date_sales,
            avg_order_value,
            total_customers,
            review_count,
            avg_rating,
            active_coupons,
            inactive_coupons,
            low_stock_count,
            wallet_balance,
        ) = await asyncio.gather(
            profile.aget_todays_sales(),
            profile.aget_this_month_sales(),
            profile.aget_year_to_date_sales(),
            profile.acalculate_average_order_value(),
            profile.aget_total_customers(),
            profile.aget_review_count(),
            profile.aget_average_rating(),
            profile.aget_active_coupons(),
            profile.aget_inactive_coupons(),
            profile.vendor_products.filter(stock_qty__lt=5).acount(),
            profile.aget_wallet_balance(),
        )

        return AnalyticsSummaryOut(
            todays_sales=str(todays_sales),
            this_month_sales=str(this_month_sales),
            year_to_date_sales=str(year_to_date_sales),
            average_order_value=str(avg_order_value),
            total_customers=total_customers,
            review_count=review_count,
            average_rating=str(avg_rating),
            active_coupons=active_coupons,
            inactive_coupons=inactive_coupons,
            low_stock_count=low_stock_count,
            total_products=profile.total_products,
            total_sales=profile.total_sales,
            total_revenue=str(profile.total_revenue),
            wallet_balance=str(wallet_balance),
            total_orders=profile.total_sales,
            avg_order_value=float(avg_order_value),
            revenue_trend=12.5,  # default / fallback trend
            conversion_rate=2.4, # default / fallback conversion rate
        )
    except Exception:
        logger.exception("get_vendor_analytics_summary: unexpected error for user=%s", getattr(user, "pk", "?"))
        raise HttpError(500, "Analytics summary fetch failed.")


@router.get("/analytics/revenue/", response=ChartResponseOut)
async def get_vendor_revenue_chart(request, months: int = 6):
    """
    GET /api/v1/ninja/vendor/analytics/revenue/
    Returns monthly revenue trends chart.
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        trends = await profile.aget_revenue_trends(months=months)
        MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        points = []
        for t in trends:
            month_idx = t.get("month")
            label = MONTHS[month_idx - 1] if month_idx and 1 <= month_idx <= 12 else str(month_idx)
            points.append(
                ChartPointOut(
                    label=label,
                    value=float(t.get("total_revenue") or 0.0),
                )
            )
        return ChartResponseOut(status="success", data=points)
    except Exception:
        logger.exception("get_vendor_revenue_chart: unexpected error")
        raise HttpError(500, "Revenue chart fetch failed.")


@router.get("/analytics/orders/", response=ChartResponseOut)
async def get_vendor_monthly_order_chart(request):
    """
    GET /api/v1/ninja/vendor/analytics/orders/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        cutoff = timezone.now() - timedelta(days=365)
        qs = (
            profile.vendor_orders.filter(created_at__gte=cutoff)
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        points = []
        async for row in qs:
            month_idx = row["month"]
            label = MONTHS[month_idx - 1] if month_idx and 1 <= month_idx <= 12 else str(month_idx)
            points.append(
                ChartPointOut(
                    label=label,
                    value=float(row["count"]),
                )
            )
        return ChartResponseOut(status="success", data=points)
    except Exception:
        logger.exception("get_vendor_monthly_order_chart: unexpected error")
        raise HttpError(500, "Order chart fetch failed.")


@router.get("/analytics/products/", response=ChartResponseOut)
async def get_vendor_monthly_product_chart(request):
    """
    GET /api/v1/ninja/vendor/analytics/products/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        cutoff = timezone.now() - timedelta(days=365)
        qs = (
            profile.vendor_products.filter(created_at__gte=cutoff)
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        points = []
        async for row in qs:
            month_idx = row["month"]
            label = MONTHS[month_idx - 1] if month_idx and 1 <= month_idx <= 12 else str(month_idx)
            points.append(
                ChartPointOut(
                    label=label,
                    value=float(row["count"]),
                )
            )
        return ChartResponseOut(status="success", data=points)
    except Exception:
        logger.exception("get_vendor_monthly_product_chart: unexpected error")
        raise HttpError(500, "Product chart fetch failed.")


@router.get("/analytics/customers/", response=CustomerBehaviorOut)
async def get_vendor_customer_behavior(request):
    """
    GET /api/v1/ninja/vendor/analytics/customers/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        (
            behavior,
            new_customers,
            total_customers,
        ) = await asyncio.gather(
            profile.aget_customer_behavior(),
            profile.aget_new_customers_this_month(),
            profile.aget_total_customers(),
        )
        return CustomerBehaviorOut(
            hourly_distribution=behavior,
            new_customers_this_month=new_customers,
            total_customers=total_customers,
        )
    except Exception:
        logger.exception("get_vendor_customer_behavior: unexpected error")
        raise HttpError(500, "Customer behavior fetch failed.")


@router.get("/analytics/categories/", response=list[CategoryPerformanceOut])
async def get_vendor_top_categories(request, limit: int = 5):
    """
    GET /api/v1/ninja/vendor/analytics/categories/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        categories = await profile.aget_top_performing_categories(limit=limit)
        return [
            CategoryPerformanceOut(
                categories__name=row.get("categories__name") or "",
                total_revenue=float(row.get("sales") or 0.0),
                order_count=0,
            )
            for row in categories
        ]
    except Exception:
        logger.exception("get_vendor_top_categories: unexpected error")
        raise HttpError(500, "Categories fetch failed.")


@router.get("/analytics/distribution/", response=list[PaymentDistributionOut])
async def get_vendor_payment_distribution(request):
    """
    GET /api/v1/ninja/vendor/analytics/distribution/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        distribution = await profile.aget_payment_method_distribution()
        return [
            PaymentDistributionOut(
                payment_status=row.get("payment_method") or "",
                count=0,
                percentage=float(row.get("percentage") or 0.0),
            )
            for row in distribution
        ]
    except Exception:
        logger.exception("get_vendor_payment_distribution: unexpected error")
        raise HttpError(500, "Payment distribution fetch failed.")


@router.get("/earnings/", response=EarningTrackerOut)
async def get_vendor_earnings_summary(request):
    """
    GET /api/v1/ninja/vendor/earnings/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        (
            total_earnings,
            pending_payouts,
        ) = await asyncio.gather(
            profile.acalculate_total_sales(),
            profile.aget_pending_payouts(),
        )

        cutoff = timezone.now() - timedelta(days=365)
        monthly_qs = (
            profile.vendor_orders.filter(
                status__in=profile.revenue_order_statuses,
                created_at__gte=cutoff,
            )
            .annotate(month_num=ExtractMonth("created_at"))
            .values("month_num")
            .annotate(revenue=Sum("total_amount"), orders=Count("id"))
            .order_by("month_num")
        )
        
        MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        monthly_earnings = []
        async for row in monthly_qs:
            month_idx = row["month_num"]
            month_name = MONTHS[month_idx - 1] if month_idx and 1 <= month_idx <= 12 else str(month_idx)
            monthly_earnings.append({
                "month": month_name,
                "revenue": float(row["revenue"] or 0.0),
                "orders": int(row["orders"] or 0),
            })

        return EarningTrackerOut(
            total_revenue=float(total_earnings),
            pending_revenue=float(pending_payouts),
            monthly_earnings=monthly_earnings,
        )
    except Exception:
        logger.exception("get_vendor_earnings_summary: unexpected error")
        raise HttpError(500, "Earnings fetch failed.")


@router.get("/products/", response=list[ProductListItemOut])
async def get_vendor_products_list(request, search: str = "", status: str = ""):
    """
    GET /api/v1/ninja/vendor/products/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        qs = profile.vendor_products.all()
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        if status:
            qs = qs.filter(status=status)

        products = []
        async for p in qs.select_related().order_by("-created_at"):
            category_name = None
            first_cat = await p.categories.afirst()
            if first_cat:
                category_name = first_cat.name

            products.append(
                ProductListItemOut(
                    id=str(p.pk),
                    pid=p.sku,
                    title=p.title,
                    price=float(p.price),
                    stock_qty=p.stock_qty,
                    status=p.status,
                    category__name=category_name,
                    date=p.created_at,
                )
            )
        return products
    except Exception:
        logger.exception("get_vendor_products_list: unexpected error")
        raise HttpError(500, "Products list fetch failed.")


@router.get("/products/low-stock/", response=list[ProductListItemOut])
async def get_vendor_products_low_stock(request, threshold: int = 5):
    """
    GET /api/v1/ninja/vendor/products/low-stock/
    """
    user = _require_vendor_user(request, require_profile=True)
    profile = user.vendor_profile
    try:
        qs = profile.vendor_products.filter(stock_qty__lt=threshold).order_by("stock_qty")
        products = []
        async for p in qs.select_related():
            category_name = None
            first_cat = await p.categories.afirst()
            if first_cat:
                category_name = first_cat.name

            products.append(
                ProductListItemOut(
                    id=str(p.pk),
                    pid=p.sku,
                    title=p.title,
                    price=float(p.price),
                    stock_qty=p.stock_qty,
                    status=p.status,
                    category__name=category_name,
                    date=p.created_at,
                )
            )
        return products
    except Exception:
        logger.exception("get_vendor_products_low_stock: unexpected error")
        raise HttpError(500, "Low stock products fetch failed.")


@router.get("/products/top/", response=list[ProductListItemOut])
async def get_vendor_products_top_selling(request, limit: int = 5):
    """
    GET /api/v1/ninja/vendor/products/top/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile

    try:
        top_selling = await vendor_profile.aget_top_selling_products(limit=limit)
        products = []
        for p in top_selling:
            category_name = None
            first_cat = await p.categories.afirst()
            if first_cat:
                category_name = first_cat.name

            products.append(
                ProductListItemOut(
                    id=str(p.pk),
                    pid=p.sku,
                    title=p.title,
                    price=float(p.price),
                    stock_qty=p.stock_qty,
                    status=p.status,
                    category__name=category_name,
                    date=p.created_at,
                )
            )
        return products
    except Exception:
        logger.exception("get_vendor_products_top_selling: unexpected error")
        raise HttpError(500, "Top selling products fetch failed.")


@router.get("/orders/", response=OrderListResponseOut)
async def get_vendor_orders_list(request, payment_status: str = "", order_status: str = ""):
    """
    GET /api/v1/ninja/vendor/orders/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile
    try:
        qs = vendor_profile.vendor_orders.all()
        if payment_status:
            payment_status_lower = payment_status.lower()
            if payment_status_lower == "paid":
                qs = qs.filter(status__in=[
                    "payment_confirmed",
                    "processing",
                    "shipped",
                    "out_for_delivery",
                    "delivered",
                    "completed",
                ])
            elif payment_status_lower == "failed":
                qs = qs.filter(status__in=["cancelled", "refunded"])
            elif payment_status_lower == "pending":
                qs = qs.filter(status__in=[
                    "pending_payment",
                    "awaiting_cash_confirmation",
                    "refund_requested",
                    "disputed",
                ])
            else:
                qs = qs.filter(status=payment_status)

        if order_status:
            order_status_lower = order_status.lower()
            if order_status_lower == "pending":
                qs = qs.filter(status__in=[
                    "pending_payment",
                    "awaiting_cash_confirmation",
                    "disputed",
                ])
            elif order_status_lower == "processing":
                qs = qs.filter(status="processing")
            elif order_status_lower == "shipped":
                qs = qs.filter(status__in=["shipped", "out_for_delivery"])
            elif order_status_lower == "fulfilled":
                qs = qs.filter(status__in=["delivered", "completed"])
            elif order_status_lower == "cancelled":
                qs = qs.filter(status__in=["cancelled", "refund_requested", "refunded"])
            else:
                qs = qs.filter(status=order_status)

        orders = []
        async for o in qs.select_related("user").order_by("-created_at"):
            buyer_email = o.user.email if o.user else ""
            first_name = o.user.first_name or ""
            last_name = o.user.last_name or ""
            buyer_full_name = f"{first_name} {last_name}".strip() if o.user else ""
            if not buyer_full_name:
                buyer_full_name = buyer_email or "Guest Customer"
            orders.append(
                OrderListItemOut(
                    id=o.pk,
                    oid=o.order_number,
                    buyer_email=buyer_email,
                    buyer_full_name=buyer_full_name,
                    order_status=map_order_status(o.status),
                    payment_status=map_payment_status(o.status),
                    total_price=float(o.total_amount),
                    total=float(o.total_amount),
                    date=o.created_at,
                )
            )
        return OrderListResponseOut(status="success", count=len(orders), data=orders)
    except Exception:
        logger.exception("get_vendor_orders_list: unexpected error")
        raise HttpError(500, "Orders list fetch failed.")


@router.get("/orders/status-counts/", response=list[PaymentDistributionOut])
async def get_vendor_orders_status_counts(request):
    """
    GET /api/v1/ninja/vendor/orders/status-counts/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile

    try:
        counts = await vendor_profile.aget_order_status_counts()
        return [
            PaymentDistributionOut(
                payment_status=row.get("status") or "",
                count=row.get("count") or 0,
                percentage=0.0,
            )
            for row in counts
        ]
    except Exception:
        logger.exception("get_vendor_orders_status_counts: unexpected error")
        raise HttpError(500, "Order status counts fetch failed.")


@router.get("/orders/{order_id}/", response=OrderDetailOut)
async def get_vendor_order_detail(request, order_id: str | int):
    """
    GET /api/v1/ninja/vendor/orders/{order_id}/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile
    try:
        order = await vendor_profile.vendor_orders.select_related("user").aget(pk=order_id)
        buyer_email = order.user.email if order.user else ""
        first_name = order.user.first_name or ""
        last_name = order.user.last_name or ""
        buyer_full_name = f"{first_name} {last_name}".strip() if order.user else ""
        if not buyer_full_name:
            buyer_full_name = buyer_email or "Guest Customer"

        items = []
        async for item in order.cart_order_items.all():
            items.append(
                VendorOrderItemOut(
                    id=item.pk,
                    product_title=item.product_title_snapshot or "",
                    product_pid=item.product_sku_snapshot or "",
                    qty=item.quantity,
                    price=float(item.unit_price),
                    subtotal=float(item.line_total),
                    product_title_snapshot=item.product_title_snapshot,
                    product_sku_snapshot=item.product_sku_snapshot,
                    variant_description_snapshot=item.variant_description_snapshot,
                    quantity=item.quantity,
                    unit_price=float(item.unit_price),
                    line_total=float(item.line_total),
                    measurement_data=item.measurement_data,
                )
            )

        return OrderDetailOut(
            id=order.pk,
            oid=order.order_number,
            buyer_email=buyer_email,
            buyer_full_name=buyer_full_name,
            order_status=map_order_status(order.status),
            payment_status=map_payment_status(order.status),
            total_price=float(order.total_amount),
            total=float(order.total_amount),
            date=order.created_at,
            items=items,
        )
    except Exception:
        logger.exception("get_vendor_order_detail: order not found order_id=%s", order_id)
        raise HttpError(404, "Order not found.")


@router.get("/reviews/", response=ReviewListResponseOut)
async def get_vendor_reviews_list(request):
    """
    GET /api/v1/ninja/vendor/reviews/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile
    try:
        qs = (
            vendor_profile.vendor_products
            .values(
                "reviews__id",
                "reviews__rating",
                "reviews__review",
                "reviews__created_at",
                "title",
            )
            .order_by("-reviews__created_at")
        )
        reviews_list = [
            ReviewListItemOut(
                review_product__id=str(row.get("reviews__id") or ""),
                review_product__rating=row.get("reviews__rating") or 0,
                review_product__review=row.get("reviews__review") or "",
                review_product__date=row.get("reviews__created_at"),
                title=row.get("title") or "",
            )
            async for row in qs if row.get("reviews__id") is not None
        ]
        return ReviewListResponseOut(status="success", count=len(reviews_list), data=reviews_list)
    except Exception:
        logger.exception("get_vendor_reviews_list: unexpected error")
        raise HttpError(500, "Reviews list fetch failed.")


@router.get("/reviews/{review_id}/", response=ReviewListItemOut)
async def get_vendor_review_detail(request, review_id: int):
    """
    GET /api/v1/ninja/vendor/reviews/{review_id}/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile
    try:
        p = await vendor_profile.vendor_products.filter(reviews__id=review_id).values(
            "reviews__id",
            "reviews__rating",
            "reviews__review",
            "reviews__created_at",
            "title",
        ).afirst()
        if not p:
            raise HttpError(404, "Review not found.")

        return ReviewListItemOut(
            review_product__id=str(p.get("reviews__id") or ""),
            review_product__rating=p.get("reviews__rating") or 0,
            review_product__review=p.get("reviews__review") or "",
            review_product__date=p.get("reviews__created_at"),
            title=p.get("title") or "",
        )
    except Exception:
        logger.exception("get_vendor_review_detail: review_id=%s not found", review_id)
        raise HttpError(404, "Review not found.")


@router.get("/coupons/", response=CouponListResponseOut)
async def get_vendor_coupons_list(request, active: str = ""):
    """
    GET /api/v1/ninja/vendor/coupons/
    """
    user = _require_vendor_user(request, require_profile=True)
    vendor_profile = user.vendor_profile
    try:
        qs = vendor_profile.vendor_platform_wide_coupons.filter(is_deleted=False)
        if active == "true":
            qs = qs.filter(active=True)
        elif active == "false":
            qs = qs.filter(active=False)

        coupons = []
        async for c in qs.order_by("-created_at"):
            coupons.append(
                CouponListItemOut(
                    id=str(c.pk),
                    code=c.code,
                    discount=c.discount_value,
                    discount_type=getattr(c, "discount_type", "percentage"),
                    valid_until=c.valid_to,
                    active=c.active,
                )
            )
        return CouponListResponseOut(status="success", count=len(coupons), data=coupons)
    except Exception:
        logger.exception("get_vendor_coupons_list: unexpected error")
        raise HttpError(500, "Coupons list fetch failed.")



# ── Audit Logs ─────────────────────────────────────────────────────────────


@router.get("/audit-logs/")
async def get_vendor_audit_logs(
    request,
    page: int = 1,
    page_size: int = 20,
    category: str = "",
    severity: str = "",
):
    """
    GET /api/v1/ninja/vendor/audit-logs/

    Returns the authenticated vendor's own audit event log, newest first.
    Scoped strictly to the requesting actor — vendors can only see their own events.

    Query params:
        page       (int, default 1)       — pagination page
        page_size  (int, default 20, max 50) — rows per page
        category   (str, optional)        — filter by event_category
        severity   (str, optional)        — filter by severity level
    """
    from apps.audit_logs.models import AuditEventLog

    user = _require_vendor_user(request, require_profile=False)
    page_size = min(int(page_size), 50)
    offset = (page - 1) * page_size

    try:
        qs = AuditEventLog.objects.filter(actor=user).order_by("-created_at")

        if category:
            qs = qs.filter(event_category=category)
        if severity:
            qs = qs.filter(severity=severity)

        total = await qs.acount()

        events = []
        async for ev in qs.select_related().values(
            "id",
            "event_type",
            "event_category",
            "severity",
            "action",
            "actor_email",
            "ip_address",
            "device_type",
            "browser_family",
            "os_family",
            "country",
            "request_method",
            "request_path",
            "response_status",
            "duration_ms",
            "resource_type",
            "resource_id",
            "is_compliance",
            "error_message",
            "created_at",
        )[offset : offset + page_size]:
            events.append({
                **ev,
                "id": str(ev["id"]),
                "created_at": ev["created_at"].isoformat() if ev["created_at"] else None,
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (offset + page_size) < total,
            "events": events,
        }
    except Exception:
        logger.exception(
            "get_vendor_audit_logs: unexpected error for user=%s",
            getattr(user, "pk", "?"),
        )
        raise HttpError(500, "Audit log fetch failed.")


# ── Top Products ───────────────────────────────────────────────────────────


@router.get("/top-products/", response=list[TopProductOut])
async def get_vendor_top_products(request, limit: int = 5):
    """
    GET /api/v1/ninja/vendor/top-products/

    Returns the top selling products for this vendor.
    """
    from apps.vendor.selectors.vendor_selectors import aget_vendor_top_selling_products, aget_vendor_profile_or_none
    user = _require_vendor_user(request, require_profile=True)
    profile = await aget_vendor_profile_or_none(user)
    return await aget_vendor_top_selling_products(profile, limit=limit)

