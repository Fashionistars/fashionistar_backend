# apps/vendor/apis/sync/analytics_views.py
"""
Vendor Analytics API — DRF Sync Views
=====================================

Provides comprehensive business intelligence and auditing tools for Vendors.
Covers sales summaries, revenue trends, product performance, and customer behavior.

URL prefix: /api/v1/vendor/

Design Principles:
  - Security: All endpoints require IsAuthenticated + Vendor-role check.
  - Performance: Uses selectors/services; avoids complex inline ORM.
  - Consistency: Standardized response formats via CustomJSONRenderer.
"""

import logging
from datetime import timedelta
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

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


# ===========================================================================
# HELPERS
# ===========================================================================


def _get_profile_or_404(user):
    """
    Retrieves the vendor profile for the given user or raises a controlled error.

    Security:
      Ensures the user is an active Vendor before returning the profile object.
    """
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


# ===========================================================================
# ANALYTICS SNAPSHOTS
# ===========================================================================


class VendorAnalyticsSummaryView(GenericAPIView):
    """
    Retrieves a high-level performance snapshot for the vendor's store.

    Validation Logic:
      - Checks for existence of vendor profile.
      - Aggregates sales, ratings, and stock alerts.

    Status Codes:
      200 OK: Returns full metrics payload.
      404 Not Found: Profile missing.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorAnalyticsSummarySerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.",
                status=status.HTTP_404_NOT_FOUND
            )

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
        serializer = self.get_serializer(data)
        return success_response(data=serializer.data)


class VendorRevenueChart(GenericAPIView):
    """
    Provides monthly revenue trends for charting.

    Query Params:
      months (int): Number of historical months to return (default: 6).

    Status Codes:
      200 OK: Returns trend data array.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorRevenueTrendSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(
                message="Vendor profile not found.",
                status=status.HTTP_404_NOT_FOUND
            )

        months = int(request.query_params.get("months", 6))
        trends = list(profile.get_revenue_trends(months=months))
        serializer = self.get_serializer(trends, many=True)
        return success_response(data=serializer.data)


# ===========================================================================
# PERFORMANCE CHARTS
# ===========================================================================


class VendorMonthlyOrderChart(GenericAPIView):
    """
    Groups order volume by month and delivery status.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorMonthlyOrderSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        from django.db.models.functions import ExtractMonth
        now = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_orders
            .filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month", "order_status")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        serializer = self.get_serializer(chart, many=True)
        return success_response(data=serializer.data)


class VendorMonthlyProductChart(GenericAPIView):
    """
    Tracks product catalog growth over time.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorMonthlyProductSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        from django.db.models.functions import ExtractMonth
        now = timezone.now()
        cutoff = now - timedelta(days=365)
        chart = list(
            profile.vendor_products
            .filter(date__gte=cutoff)
            .annotate(month=ExtractMonth("date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        serializer = self.get_serializer(chart, many=True)
        return success_response(data=serializer.data)


# ===========================================================================
# EARNINGS & BEHAVIOR
# ===========================================================================


class VendorEarningTrackerView(GenericAPIView):
    """
    Detailed earning tracker including pending payouts and historical sales.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorEarningTrackerSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
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
        serializer = self.get_serializer(data)
        return success_response(data=serializer.data)


class VendorCustomerBehaviorView(GenericAPIView):
    """
    Analyzes customer engagement times and acquisition rates.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCustomerBehaviorSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        data = {
            "hourly_distribution":      list(profile.get_customer_behavior()),
            "new_customers_this_month": profile.get_new_customers_this_month(),
            "total_customers":          profile.get_total_customers(),
        }
        serializer = self.get_serializer(data)
        return success_response(data=serializer.data)


class VendorTopCategoriesView(GenericAPIView):
    """
    Ranks product categories by their contribution to total revenue.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCategoryPerformanceSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        limit = int(request.query_params.get("limit", 5))
        data = profile.get_top_performing_categories(limit=limit)
        serializer = self.get_serializer(data, many=True)
        return success_response(data=serializer.data)


class VendorPaymentDistributionView(GenericAPIView):
    """
    Breaks down revenue by payment methods and statuses.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPaymentDistributionSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        data = profile.get_payment_method_distribution()
        serializer = self.get_serializer(data, many=True)
        return success_response(data=serializer.data)


# ===========================================================================
# PRODUCT INVENTORY VIEWS
# ===========================================================================


class VendorProductListView(ListAPIView):
    """
    Standard inventory listing for the Vendor portal.

    Supports:
      - Search by title/description.
      - Status filtering (active/inactive).
    """
    permission_classes = [IsAuthenticated]
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
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.values("id", "title", "price", "stock_qty", "status", "category__name", "date").order_by("-date")


class VendorLowStockView(ListAPIView):
    """
    Identifies products with inventory levels below the specified threshold.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        threshold = int(self.request.query_params.get("threshold", 5))
        return profile.get_low_stock_alerts(threshold=threshold).values(
            "id", "title", "price", "stock_qty", "status", "category__name", "date"
        ).order_by("stock_qty")


class VendorTopSellingProductsView(ListAPIView):
    """
    Lists the Vendor's highest-grossing products.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorProductListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except (ValueError, AttributeError):
            return []

        limit = int(self.request.query_params.get("limit", 5))
        return profile.get_top_selling_products(limit=limit).values(
            "id", "title", "price", "stock_qty", "status", "category__name", "date"
        )


# ===========================================================================
# ORDER MANAGEMENT VIEWS
# ===========================================================================


class VendorOrderListView(ListAPIView):
    """
    Retrieves history of orders placed at the Vendor's store.
    """
    permission_classes = [IsAuthenticated]
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

        return qs.values("id", "total", "payment_status", "order_status", "date", "buyer__email").order_by("-date")


class VendorOrderDetailView(RetrieveAPIView):
    """
    Granular details for a specific incoming order.
    """
    permission_classes = [IsAuthenticated]
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
            return {
                "id":              order.pk,
                "total":           str(order.total),
                "payment_status":  order.payment_status,
                "order_status":    order.order_status,
                "date":            order.date,
                "buyer_email":     getattr(order.buyer, "email", ""),
            }
        except profile.vendor_orders.model.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Order not found.")


class VendorOrderStatusCountsView(GenericAPIView):
    """
    Provides counts of orders segmented by their current fulfillment status.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPaymentDistributionSerializer

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
        except (ValueError, AttributeError):
            return error_response(message="Vendor profile not found.", status=status.HTTP_404_NOT_FOUND)

        counts = list(profile.get_order_status_counts())
        serializer = self.get_serializer(counts, many=True)
        return success_response(data=serializer.data)


# ===========================================================================
# REVIEW & REPUTATION VIEWS
# ===========================================================================


class VendorReviewListView(ListAPIView):
    """
    Aggregates all reviews and ratings received across the entire catalog.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorReviewListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_products.values(
                "review_product__id",
                "review_product__rating",
                "review_product__review",
                "review_product__date",
                "title",
            ).order_by("-review_product__date")
        except (ValueError, AttributeError):
            return []


class VendorReviewDetailView(RetrieveAPIView):
    """
    Specific review analysis and metadata.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorReviewListSerializer
    lookup_field = "review_id"

    def get_object(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            review_id = self.kwargs.get(self.lookup_field)
            review_data = (
                profile.vendor_products
                .filter(review_product__id=review_id)
                .values(
                    "review_product__id", "review_product__rating",
                    "review_product__review", "review_product__date", "title",
                )
                .first()
            )
            if not review_data:
                from rest_framework.exceptions import NotFound
                raise NotFound("Review not found.")
            return review_data
        except (ValueError, AttributeError):
            from rest_framework.exceptions import NotFound
            raise NotFound("Vendor profile not found.")


# ===========================================================================
# PROMOTIONS & COUPONS
# ===========================================================================


class VendorCouponListView(ListAPIView):
    """
    Lists and filters Vendor-specific discount codes.

    Query Params:
      active (bool): Filter by activation status.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorCouponListSerializer

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            active_param = self.request.query_params.get("active", "").strip().lower()
            qs = profile.vendor_coupons.all()
            if active_param == "true":
                qs = qs.filter(active=True)
            elif active_param == "false":
                qs = qs.filter(active=False)

            return qs.values("id", "code", "discount", "date", "active").order_by("-date")
        except (ValueError, AttributeError):
            return []
