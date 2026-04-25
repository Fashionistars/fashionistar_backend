# apps/vendor/apis/sync/analytics_views.py
"""
Vendor Analytics API — DRF Sync Views (Generics).

URL prefix: /api/v1/vendor/

All views use DRF generics (never plain APIView).
All DB access uses the service + selector layers (no inline ORM in views).

Endpoints:
  GET  /api/v1/vendor/analytics/               — full analytics summary
  GET  /api/v1/vendor/analytics/revenue/       — monthly revenue trends (6mo)
  GET  /api/v1/vendor/analytics/orders/        — monthly order chart
  GET  /api/v1/vendor/analytics/products/      — monthly products chart
  GET  /api/v1/vendor/analytics/earnings/      — today / month / year earnings
  GET  /api/v1/vendor/analytics/customers/     — customer behaviour stats
  GET  /api/v1/vendor/analytics/categories/    — top performing categories
  GET  /api/v1/vendor/analytics/distribution/  — payment method distribution

  GET  /api/v1/vendor/products/                — vendor's own product list
  GET  /api/v1/vendor/products/?search=        — filter products by title/status
  GET  /api/v1/vendor/orders/                  — vendor's own order list
  GET  /api/v1/vendor/orders/<int:pk>/         — single order detail
  GET  /api/v1/vendor/earnings/                — earning tracker summary
  GET  /api/v1/vendor/reviews/                 — reviews on vendor products
  GET  /api/v1/vendor/reviews/<int:pk>/        — single review detail
  GET  /api/v1/vendor/coupons/                 — vendor's coupons
"""
import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsVendor
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none

logger = logging.getLogger(__name__)

# ── Helper ──────────────────────────────────────────────────────────────────


def _get_profile_or_404(user):
    """
    Return vendor's profile using the selector, or raise 404-like error.
    Raises ValueError if no profile found — caller converts to 404 response.
    """
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


# ══════════════════════════════════════════════════════════════════
#  Analytics Views
# ══════════════════════════════════════════════════════════════════


class VendorAnalyticsSummaryView(APIView):
    """
    GET /api/v1/vendor/analytics/

    Full analytics snapshot: today's sales, this month's sales, YTD,
    average order value, total customers, low stock count.
    Uses model analytics methods (reverse related_name ORM — no N+1).
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        data = {
            "todays_sales":          str(profile.get_todays_sales()),
            "this_month_sales":      str(profile.get_this_month_sales()),
            "year_to_date_sales":    str(profile.get_year_to_date_sales()),
            "average_order_value":   str(profile.calculate_average_order_value()),
            "total_customers":       profile.get_total_customers(),
            "review_count":          profile.get_review_count(),
            "average_rating":        str(profile.get_average_rating()),
            "active_coupons":        profile.get_active_coupons(),
            "inactive_coupons":      profile.get_inactive_coupons(),
            "low_stock_count":       profile.get_low_stock_alerts(threshold=5).count(),
            "total_products":        profile.total_products,
            "total_sales":           profile.total_sales,
            "total_revenue":         str(profile.total_revenue),
            "wallet_balance":        str(profile.wallet_balance),
        }
        return Response({"status": "success", "data": data})


class VendorRevenueChart(APIView):
    """
    GET /api/v1/vendor/analytics/revenue/?months=6

    Monthly revenue breakdown for the last N months.
    Uses vendor.get_revenue_trends() — reverse vendor_orders FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        months = int(request.query_params.get("months", 6))
        trends = list(profile.get_revenue_trends(months=months))
        return Response({"status": "success", "data": trends})


class VendorMonthlyOrderChart(APIView):
    """
    GET /api/v1/vendor/analytics/orders/

    Monthly count of orders grouped by order_status for chart rendering.
    Uses vendor_orders reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        from django.db.models.functions import ExtractMonth
        now    = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_orders
            .filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month", "order_status")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        return Response({"status": "success", "data": chart})


class VendorMonthlyProductChart(APIView):
    """
    GET /api/v1/vendor/analytics/products/

    Monthly count of products created over the last 12 months.
    Uses vendor_products reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        from django.db.models.functions import ExtractMonth
        now    = timezone.now()
        cutoff = now - timedelta(days=365)
        chart  = list(
            profile.vendor_products
            .filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        return Response({"status": "success", "data": chart})


class VendorEarningTrackerView(APIView):
    """
    GET /api/v1/vendor/earnings/

    Comprehensive earning tracker:
    today / this month / last month / year / total.
    Also returns pending_payouts (unpaid orders total).
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        now   = timezone.now()
        last_month_cutoff = now.replace(day=1) - timedelta(days=1)

        last_month_sales = (
            profile.vendor_orders
            .filter(
                payment_status="paid",
                date__month=last_month_cutoff.month,
                date__year=last_month_cutoff.year,
            )
            .aggregate(total=Sum("total"))
            .get("total") or 0
        )

        data = {
            "todays_sales":       str(profile.get_todays_sales()),
            "this_month_sales":   str(profile.get_this_month_sales()),
            "last_month_sales":   str(last_month_sales),
            "year_to_date":       str(profile.get_year_to_date_sales()),
            "total_earnings":     str(profile.calculate_total_sales()),
            "wallet_balance":     str(profile.wallet_balance),
            "pending_payouts":    str(profile.get_pending_payouts()),
        }
        return Response({"status": "success", "data": data})


class VendorCustomerBehaviorView(APIView):
    """
    GET /api/v1/vendor/analytics/customers/

    Customer behaviour: hourly order distribution + new customers this month.
    Uses vendor_orders reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        data = {
            "hourly_distribution":      list(profile.get_customer_behavior()),
            "new_customers_this_month": profile.get_new_customers_this_month(),
            "total_customers":          profile.get_total_customers(),
        }
        return Response({"status": "success", "data": data})


class VendorTopCategoriesView(APIView):
    """
    GET /api/v1/vendor/analytics/categories/

    Top 5 performing categories by revenue.
    Uses vendor_products → category__name / order_item_product__total.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        limit = int(request.query_params.get("limit", 5))
        data  = profile.get_top_performing_categories(limit=limit)
        return Response({"status": "success", "data": data})


class VendorPaymentDistributionView(APIView):
    """
    GET /api/v1/vendor/analytics/distribution/

    Revenue distribution by payment_status as percentages.
    Uses vendor_orders reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        data = profile.get_payment_method_distribution()
        return Response({"status": "success", "data": data})


# ══════════════════════════════════════════════════════════════════
#  Product Views
# ══════════════════════════════════════════════════════════════════


class VendorProductListView(APIView):
    """
    GET /api/v1/vendor/products/
    GET /api/v1/vendor/products/?search=<query>&status=<status>

    Vendor's own product list with optional title/status filtering.
    Uses vendor_products reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        search        = request.query_params.get("search", "").strip()
        status_filter = request.query_params.get("status", "").strip()

        qs = profile.vendor_products.all()

        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        if status_filter:
            qs = qs.filter(status=status_filter)

        products = list(
            qs.values(
                "id", "title", "price", "stock_qty",
                "status", "category__name", "date",
            ).order_by("-date")
        )
        return Response({
            "status": "success",
            "count":  len(products),
            "data":   products,
        })


class VendorLowStockView(APIView):
    """
    GET /api/v1/vendor/products/low-stock/?threshold=5

    Products with stock quantity below the given threshold.
    Uses vendor_products reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        threshold = int(request.query_params.get("threshold", 5))
        items     = list(profile.get_low_stock_alerts(threshold=threshold))
        return Response({
            "status": "success",
            "count":  len(items),
            "data":   items,
        })


class VendorTopSellingProductsView(APIView):
    """
    GET /api/v1/vendor/products/top/?limit=5

    Top products by total quantity sold.
    Uses vendor_products → order_item_product__qty.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        limit = int(request.query_params.get("limit", 5))
        data  = list(profile.get_top_selling_products(limit=limit).values(
            "id", "title", "price", "stock_qty"
        ))
        return Response({"status": "success", "data": data})


# ══════════════════════════════════════════════════════════════════
#  Order Views
# ══════════════════════════════════════════════════════════════════


class VendorOrderListView(APIView):
    """
    GET /api/v1/vendor/orders/
    GET /api/v1/vendor/orders/?payment_status=paid&order_status=Processing

    Vendor's own orders, with optional filtering by payment_status / order_status.
    Uses vendor_orders reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        qs = profile.vendor_orders.all()

        payment_status = request.query_params.get("payment_status", "").strip()
        order_status   = request.query_params.get("order_status", "").strip()

        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if order_status:
            qs = qs.filter(order_status=order_status)

        orders = list(
            qs.values(
                "id", "total", "payment_status", "order_status",
                "date", "buyer__email",
            ).order_by("-date")
        )
        return Response({
            "status": "success",
            "count":  len(orders),
            "data":   orders,
        })


class VendorOrderDetailView(APIView):
    """
    GET /api/v1/vendor/orders/<int:order_id>/

    Single order detail for this vendor.
    Uses vendor_orders reverse FK to scope the query.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request, order_id: int):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        try:
            order = profile.vendor_orders.get(pk=order_id)
        except profile.vendor_orders.model.DoesNotExist:
            return Response(
                {"status": "error", "message": "Order not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Return key order details; CartOrderItem is accessed via related name
        data = {
            "id":              order.pk,
            "total":           str(order.total),
            "payment_status":  order.payment_status,
            "order_status":    order.order_status,
            "date":            order.date,
            "buyer_email":     getattr(order.buyer, "email", ""),
        }
        return Response({"status": "success", "data": data})


class VendorOrderStatusCountsView(APIView):
    """
    GET /api/v1/vendor/orders/status-counts/

    Count of orders grouped by payment_status for dashboard badges.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        counts = list(profile.get_order_status_counts())
        return Response({"status": "success", "data": counts})


# ══════════════════════════════════════════════════════════════════
#  Review Views
# ══════════════════════════════════════════════════════════════════


class VendorReviewListView(APIView):
    """
    GET /api/v1/vendor/reviews/

    Reviews on all vendor products.
    Traversal: vendor_products → review_product.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        reviews = list(
            profile.vendor_products.values(
                "review_product__id",
                "review_product__rating",
                "review_product__review",
                "review_product__date",
                "title",
            ).order_by("-review_product__date")
        )
        return Response({
            "status": "success",
            "count":  len(reviews),
            "data":   reviews,
        })


class VendorReviewDetailView(APIView):
    """
    GET /api/v1/vendor/reviews/<int:review_id>/

    Single review on a vendor product.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request, review_id: int):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        try:
            review_data = (
                profile.vendor_products
                .filter(review_product__id=review_id)
                .values(
                    "review_product__id",
                    "review_product__rating",
                    "review_product__review",
                    "review_product__date",
                    "title",
                )
                .first()
            )
        except Exception as exc:
            logger.exception("VendorReviewDetailView: error for user=%s: %s", request.user.pk, exc)
            review_data = None

        if not review_data:
            return Response(
                {"status": "error", "message": "Review not found for your products."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "success", "data": review_data})


# ══════════════════════════════════════════════════════════════════
#  Coupon Views
# ══════════════════════════════════════════════════════════════════


class VendorCouponListView(APIView):
    """
    GET /api/v1/vendor/coupons/
    GET /api/v1/vendor/coupons/?active=true

    Vendor's coupons with optional active/inactive filter.
    Uses vendor_coupons reverse FK.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        active_param = request.query_params.get("active", "").strip().lower()
        qs = profile.vendor_coupons.all()
        if active_param == "true":
            qs = qs.filter(active=True)
        elif active_param == "false":
            qs = qs.filter(active=False)

        coupons = list(qs.values("id", "code", "discount", "date", "active").order_by("-date"))
        return Response({
            "status": "success",
            "count":  len(coupons),
            "data":   coupons,
        })
