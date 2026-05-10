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
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from apps.vendor.serializers.vendor_analytics_serializers import (
    VendorAnalyticsSummarySerializer,
    VendorRevenueTrendSerializer,
    VendorMonthlyOrderSerializer,
    VendorMonthlyProductSerializer,
    VendorEarningTrackerSerializer,
    VendorCustomerBehaviorSerializer,
    VendorCategoryPerformanceSerializer,
    VendorPaymentDistributionSerializer,
    VendorProductListSerializer,
    VendorOrderListSerializer,
    VendorOrderDetailSerializer,
    VendorReviewListSerializer,
    VendorCouponListSerializer,
)

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


class VendorAnalyticsSummaryView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/

    Full analytics snapshot: today's sales, this month's sales, YTD,
    average order value, total customers, low stock count.
    Uses model analytics methods (reverse related_name ORM — no N+1).
    Full analytics snapshot.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorAnalyticsSummarySerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = {
            "todays_sales": str(profile.get_todays_sales()),
            "this_month_sales": str(profile.get_this_month_sales()),
            "year_to_date_sales": str(profile.get_year_to_date_sales()),
            "average_order_value": str(profile.calculate_average_order_value()),
            "total_customers": profile.get_total_customers(),
            "review_count": profile.get_review_count(),
            "average_rating": str(profile.get_average_rating()),
            "active_coupons": profile.get_active_coupons(),
            "inactive_coupons": profile.get_inactive_coupons(),
            "low_stock_count": profile.get_low_stock_alerts(threshold=5).count(),
            "total_products": profile.total_products,
            "total_sales": profile.total_sales,
            "total_revenue": str(profile.total_revenue),
            "wallet_balance": str(profile.wallet_balance),
        }
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class VendorRevenueChart(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/revenue/?months=6

    Monthly revenue breakdown for the last N months.
    Uses vendor.get_revenue_trends() — reverse vendor_orders FK.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorRevenueTrendSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        months = int(request.query_params.get("months", 6))
        trends = list(profile.get_revenue_trends(months=months))
        serializer = self.get_serializer(trends, many=True)
        return Response(serializer.data)


class VendorMonthlyOrderChart(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/orders/

    Monthly count of orders grouped by order_status for chart rendering.
    Uses vendor_orders reverse FK.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorMonthlyOrderSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from django.db.models.functions import ExtractMonth

        now = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_orders.filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month", "order_status")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        serializer = self.get_serializer(chart, many=True)
        return Response(serializer.data)


class VendorMonthlyProductChart(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/products/

    Monthly count of products created over the last 12 months.
    Uses vendor_products reverse FK.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorMonthlyProductSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from django.db.models.functions import ExtractMonth

        now = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_products.filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        serializer = self.get_serializer(chart, many=True)
        return Response(serializer.data)


class VendorEarningTrackerView(GenericAPIView):
    """
    GET /api/v1/vendor/earnings/

    Comprehensive earning tracker:
    today / this month / last month / year / total.
    Also returns pending_payouts (unpaid orders total).
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorEarningTrackerSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        now = timezone.now()
        last_month_cutoff = now.replace(day=1) - timedelta(days=1)

        last_month_sales = (
            profile.vendor_orders.filter(
                payment_status="paid",
                date__month=last_month_cutoff.month,
                date__year=last_month_cutoff.year,
            )
            .aggregate(total=Sum("total"))
            .get("total")
            or 0
        )

        data = {
            "todays_sales": str(profile.get_todays_sales()),
            "this_month_sales": str(profile.get_this_month_sales()),
            "last_month_sales": str(last_month_sales),
            "year_to_date": str(profile.get_year_to_date_sales()),
            "total_earnings": str(profile.calculate_total_sales()),
            "wallet_balance": str(profile.wallet_balance),
            "pending_payouts": str(profile.get_pending_payouts()),
        }
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class VendorCustomerBehaviorView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/customers/

    Customer behaviour: hourly order distribution + new customers this month.
    Uses vendor_orders reverse FK.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCustomerBehaviorSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = {
            "hourly_distribution": list(profile.get_customer_behavior()),
            "new_customers_this_month": profile.get_new_customers_this_month(),
            "total_customers": profile.get_total_customers(),
        }
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class VendorTopCategoriesView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/categories/

    Top 5 performing categories by revenue.
    Uses vendor_products → categories__name / order_item_product__total.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCategoryPerformanceSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        limit = int(request.query_params.get("limit", 5))
        data = profile.get_top_performing_categories(limit=limit)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)


class VendorPaymentDistributionView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/distribution/

    Revenue distribution by payment_status as percentages.
    Uses vendor_orders reverse FK.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPaymentDistributionSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = profile.get_payment_method_distribution()
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)


# ══════════════════════════════════════════════════════════════════
#  Product Views
# ══════════════════════════════════════════════════════════════════


class VendorProductListView(ListAPIView):
    """
    GET /api/v1/vendor/products/
    GET /api/v1/vendor/products/?search=<query>&status=<status>

    Vendor's own product list with optional title/status filtering.
    Uses vendor_products reverse FK.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        search = self.request.query_params.get("search", "").strip()
        status_filter = self.request.query_params.get("status", "").strip()

        qs = profile.vendor_products.all()

        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        if status_filter:
            qs = qs.filter(status=status_filter)

        products = list(
            qs.values(
                "id",
                "title",
                "price",
                "stock_qty",
                "status",
                "categories__name",
                "date",
            ).order_by("-date")
        )
        return Response(
            {
                "status": "success",
                "count": len(products),
                "data": products,
            }
        )


class VendorLowStockView(ListAPIView):
    """
    GET /api/v1/vendor/products/low-stock/?threshold=5

    Products with stock quantity below the given threshold.
    Uses vendor_products reverse FK.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer  # Reusing list serializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        threshold = int(self.request.query_params.get("threshold", 5))
        return (
            profile.get_low_stock_alerts(threshold=threshold)
            .values(
                "id",
                "title",
                "price",
                "stock_qty",
                "status",
                "categories__name",
                "date",
            )
            .order_by("stock_qty")
        )


class VendorTopSellingProductsView(ListAPIView):
    """
    GET /api/v1/vendor/products/top/?limit=5

    Top products by total quantity sold.
    Uses vendor_products → order_item_product__qty.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        limit = int(self.request.query_params.get("limit", 5))
        return profile.get_top_selling_products(limit=limit).values(
            "id",
            "title",
            "price",
            "stock_qty",
            "status",
            "categories__name",
            "date",
        )


# ══════════════════════════════════════════════════════════════════
#  Order Views
# ══════════════════════════════════════════════════════════════════


class VendorOrderListView(ListAPIView):
    """
    GET /api/v1/vendor/orders/
    GET /api/v1/vendor/orders/?payment_status=paid&order_status=Processing

    Vendor's own orders, with optional filtering by payment_status / order_status.
    Uses vendor_orders reverse FK.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorOrderListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        qs = profile.vendor_orders.all()
        payment_status = self.request.query_params.get("payment_status", "").strip()
        order_status = self.request.query_params.get("order_status", "").strip()

        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if order_status:
            qs = qs.filter(order_status=order_status)

        return qs.values(
            "id",
            "total",
            "payment_status",
            "order_status",
            "date",
            "buyer__email",
        ).order_by("-date")


class VendorOrderDetailView(RetrieveAPIView):
    """
    GET /api/v1/vendor/orders/<int:order_id>/

    Single order detail for this vendor.
    Uses vendor_orders reverse FK to scope the query.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorOrderDetailSerializer
    lookup_field = "id"
    lookup_url_kwarg = "order_id"

    def get_object(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            raise status.HTTP_404_NOT_FOUND

        order_id = self.kwargs.get(self.lookup_url_kwarg)
        try:
            order = profile.vendor_orders.get(pk=order_id)
        except profile.vendor_orders.model.DoesNotExist:
            raise status.HTTP_404_NOT_FOUND

        return {
            "id": order.pk,
            "total": str(order.total),
            "payment_status": order.payment_status,
            "order_status": order.order_status,
            "date": order.date,
            "buyer_email": getattr(order.buyer, "email", ""),
        }


class VendorOrderStatusCountsView(GenericAPIView):
    """
    GET /api/v1/vendor/orders/status-counts/

    Count of orders grouped by payment_status for dashboard badges.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPaymentDistributionSerializer  # Reusing structure

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return Response(
                {"message": "Vendor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        counts = list(profile.get_order_status_counts())
        serializer = self.get_serializer(counts, many=True)
        return Response(serializer.data)


# ══════════════════════════════════════════════════════════════════
#  Review Views
# ══════════════════════════════════════════════════════════════════


class VendorReviewListView(ListAPIView):
    """
    GET /api/v1/vendor/reviews/

    Reviews on all vendor products.
    Traversal: vendor_products → review_product.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorReviewListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        return profile.vendor_products.values(
            "review_product__id",
            "review_product__rating",
            "review_product__review",
            "review_product__date",
            "title",
        ).order_by("-review_product__date")


class VendorReviewDetailView(RetrieveAPIView):
    """
    GET /api/v1/vendor/reviews/<int:review_id>/

    Single review on a vendor product.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorReviewListSerializer
    lookup_field = "review_id"

    def get_object(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            raise status.HTTP_404_NOT_FOUND

        review_id = self.kwargs.get(self.lookup_field)
        review_data = (
            profile.vendor_products.filter(review_product__id=review_id)
            .values(
                "review_product__id",
                "review_product__rating",
                "review_product__review",
                "review_product__date",
                "title",
            )
            .first()
        )
        if not review_data:
            raise status.HTTP_404_NOT_FOUND
        return review_data


# ══════════════════════════════════════════════════════════════════
#  Coupon Views
# ══════════════════════════════════════════════════════════════════


class VendorCouponListView(ListAPIView):
    """
    GET /api/v1/vendor/coupons/
    GET /api/v1/vendor/coupons/?active=true

    Vendor's coupons with optional active/inactive filter.
    Uses vendor_coupons reverse FK.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCouponListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        active_param = self.request.query_params.get("active", "").strip().lower()
        qs = profile.vendor_coupons.all()
        if active_param == "true":
            qs = qs.filter(active=True)
        elif active_param == "false":
            qs = qs.filter(active=False)

        return qs.values("id", "code", "discount", "date", "active").order_by("-date")


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
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from apps.vendor.serializers.vendor_analytics_serializers import (
    VendorAnalyticsSummarySerializer,
    VendorRevenueTrendSerializer,
    VendorMonthlyOrderSerializer,
    VendorMonthlyProductSerializer,
    VendorEarningTrackerSerializer,
    VendorCustomerBehaviorSerializer,
    VendorCategoryPerformanceSerializer,
    VendorPaymentDistributionSerializer,
    VendorProductListSerializer,
    VendorOrderListSerializer,
    VendorOrderDetailSerializer,
    VendorReviewListSerializer,
    VendorCouponListSerializer,
)

logger = logging.getLogger(__name__)

# ── Helper ──────────────────────────────────────────────────────────────────


def _get_profile_or_404(user):
    """
    Return vendor's profile using the selector, or raise 404-like error.
    """
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


# ══════════════════════════════════════════════════════════════════
#  Analytics Views
# ══════════════════════════════════════════════════════════════════


class VendorAnalyticsSummaryView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/
    Full analytics snapshot.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorAnalyticsSummarySerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        data = {
            "todays_sales": str(profile.get_todays_sales()),
            "this_month_sales": str(profile.get_this_month_sales()),
            "year_to_date_sales": str(profile.get_year_to_date_sales()),
            "average_order_value": str(profile.calculate_average_order_value()),
            "total_customers": profile.get_total_customers(),
            "review_count": profile.get_review_count(),
            "average_rating": str(profile.get_average_rating()),
            "active_coupons": profile.get_active_coupons(),
            "inactive_coupons": profile.get_inactive_coupons(),
            "low_stock_count": profile.get_low_stock_alerts(threshold=5).count(),
            "total_products": profile.total_products,
            "total_sales": profile.total_sales,
            "total_revenue": str(profile.total_revenue),
            "wallet_balance": str(profile.wallet_balance),
        }
        serializer = self.get_serializer(data)
        return success_response(data=serializer.data)


class VendorRevenueChart(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/revenue/?months=6
    Monthly revenue breakdown.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorRevenueTrendSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        months = int(request.query_params.get("months", 6))
        trends = list(profile.get_revenue_trends(months=months))
        serializer = self.get_serializer(trends, many=True)
        return success_response(data=serializer.data)


class VendorMonthlyOrderChart(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/orders/
    Monthly count of orders grouped by order_status.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorMonthlyOrderSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        from django.db.models.functions import ExtractMonth

        now = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_orders.filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month", "order_status")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        serializer = self.get_serializer(chart, many=True)
        return success_response(data=serializer.data)


class VendorMonthlyProductChart(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/products/
    Monthly count of products created.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorMonthlyProductSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        from django.db.models.functions import ExtractMonth

        now = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_products.filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        serializer = self.get_serializer(chart, many=True)
        return success_response(data=serializer.data)


class VendorEarningTrackerView(GenericAPIView):
    """
    GET /api/v1/vendor/earnings/
    Comprehensive earning tracker.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorEarningTrackerSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        now = timezone.now()
        last_month_cutoff = now.replace(day=1) - timedelta(days=1)

        last_month_sales = (
            profile.vendor_orders.filter(
                payment_status="paid",
                date__month=last_month_cutoff.month,
                date__year=last_month_cutoff.year,
            )
            .aggregate(total=Sum("total"))
            .get("total")
            or 0
        )

        data = {
            "todays_sales": str(profile.get_todays_sales()),
            "this_month_sales": str(profile.get_this_month_sales()),
            "last_month_sales": str(last_month_sales),
            "year_to_date": str(profile.get_year_to_date_sales()),
            "total_earnings": str(profile.calculate_total_sales()),
            "wallet_balance": str(profile.wallet_balance),
            "pending_payouts": str(profile.get_pending_payouts()),
        }
        serializer = self.get_serializer(data)
        return success_response(data=serializer.data)


class VendorCustomerBehaviorView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/customers/
    Customer behaviour analysis.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCustomerBehaviorSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        data = {
            "hourly_distribution": list(profile.get_customer_behavior()),
            "new_customers_this_month": profile.get_new_customers_this_month(),
            "total_customers": profile.get_total_customers(),
        }
        serializer = self.get_serializer(data)
        return success_response(data=serializer.data)


class VendorTopCategoriesView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/categories/
    Top performing categories.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCategoryPerformanceSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        limit = int(request.query_params.get("limit", 5))
        data = profile.get_top_performing_categories(limit=limit)
        serializer = self.get_serializer(data, many=True)
        return success_response(data=serializer.data)


class VendorPaymentDistributionView(GenericAPIView):
    """
    GET /api/v1/vendor/analytics/distribution/
    Revenue distribution by payment status.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPaymentDistributionSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        data = profile.get_payment_method_distribution()
        serializer = self.get_serializer(data, many=True)
        return success_response(data=serializer.data)


# ── Product Views ───────────────────────────────────────────────────────────


class VendorProductListView(ListAPIView):
    """
    GET /api/v1/vendor/products/
    Vendor's own product list.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return Product.objects.none()

        search = self.request.query_params.get("search", "").strip()
        status_filter = self.request.query_params.get("status", "").strip()

        qs = profile.vendor_products.all()

        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.values(
            "id",
            "title",
            "price",
            "stock_qty",
            "status",
            "categories__name",
            "date",
        ).order_by("-date")


class VendorLowStockView(ListAPIView):
    """
    GET /api/v1/vendor/products/low-stock/?threshold=5
    Low stock alerts.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer  # Reusing list serializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return Product.objects.none()

        threshold = int(self.request.query_params.get("threshold", 5))
        return (
            profile.get_low_stock_alerts(threshold=threshold)
            .values(
                "id",
                "title",
                "price",
                "stock_qty",
                "status",
                "categories__name",
                "date",
            )
            .order_by("stock_qty")
        )


class VendorTopSellingProductsView(ListAPIView):
    """
    GET /api/v1/vendor/products/top/?limit=5
    Top products by sales.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return Product.objects.none()

        limit = int(self.request.query_params.get("limit", 5))
        return profile.get_top_selling_products(limit=limit).values(
            "id",
            "title",
            "price",
            "stock_qty",
            "status",
            "categories__name",
            "date",
        )


# ── Order Views ─────────────────────────────────────────────────────────────


class VendorOrderListView(ListAPIView):
    """
    GET /api/v1/vendor/orders/
    Vendor's own order list.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorOrderListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return CartOrder.objects.none()

        qs = profile.vendor_orders.all()
        payment_status = self.request.query_params.get("payment_status", "").strip()
        order_status = self.request.query_params.get("order_status", "").strip()

        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if order_status:
            qs = qs.filter(order_status=order_status)

        return qs.values(
            "id",
            "total",
            "payment_status",
            "order_status",
            "date",
            "buyer__email",
        ).order_by("-date")


class VendorOrderDetailView(RetrieveAPIView):
    """
    GET /api/v1/vendor/orders/<int:pk>/
    Single order detail.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorOrderDetailSerializer
    lookup_field = "id"
    lookup_url_kwarg = "order_id"

    def get_object(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            from rest_framework.exceptions import NotFound

            raise NotFound("Vendor profile not found.")

        order_id = self.kwargs.get(self.lookup_url_kwarg)
        try:
            order = profile.vendor_orders.get(pk=order_id)
        except profile.vendor_orders.model.DoesNotExist:
            from rest_framework.exceptions import NotFound

            raise NotFound("Order not found.")

        return {
            "id": order.pk,
            "total": str(order.total),
            "payment_status": order.payment_status,
            "order_status": order.order_status,
            "date": order.date,
            "buyer_email": getattr(order.buyer, "email", ""),
        }


class VendorOrderStatusCountsView(GenericAPIView):
    """
    GET /api/v1/vendor/orders/status-counts/
    Order counts by status.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPaymentDistributionSerializer  # Reusing structure

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND
            )

        counts = list(profile.get_order_status_counts())
        serializer = self.get_serializer(counts, many=True)
        return success_response(data=serializer.data)


# ── Review Views ────────────────────────────────────────────────────────────


class VendorReviewListView(ListAPIView):
    """
    GET /api/v1/vendor/reviews/
    Reviews on all vendor products.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorReviewListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        return profile.vendor_products.values(
            "review_product__id",
            "review_product__rating",
            "review_product__review",
            "review_product__date",
            "title",
        ).order_by("-review_product__date")


class VendorReviewDetailView(RetrieveAPIView):
    """
    GET /api/v1/vendor/reviews/<int:pk>/
    Single review detail.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorReviewListSerializer
    lookup_field = "review_id"

    def get_object(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            from rest_framework.exceptions import NotFound

            raise NotFound("Vendor profile not found.")

        review_id = self.kwargs.get(self.lookup_field)
        review_data = (
            profile.vendor_products.filter(review_product__id=review_id)
            .values(
                "review_product__id",
                "review_product__rating",
                "review_product__review",
                "review_product__date",
                "title",
            )
            .first()
        )
        if not review_data:
            from rest_framework.exceptions import NotFound

            raise NotFound("Review not found.")
        return review_data


# ── Coupon Views ────────────────────────────────────────────────────────────


class VendorCouponListView(ListAPIView):
    """
    GET /api/v1/vendor/coupons/
    Vendor's coupons.
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCouponListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        active_param = self.request.query_params.get("active", "").strip().lower()
        qs = profile.vendor_coupons.all()
        if active_param == "true":
            qs = qs.filter(active=True)
        elif active_param == "false":
            qs = qs.filter(active=False)

        return qs.values("id", "code", "discount", "date", "active").order_by("-date")
