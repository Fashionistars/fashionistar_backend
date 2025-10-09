# vendor/Views/dashboard.py

import logging


from rest_framework import status
from rest_framework import generics
from rest_framework.response import Response

# ... (other imports)
from rest_framework.permissions import IsAuthenticated

# Import custom components from vendor app (adjusted for correct paths)
from vendor.serializerss.dashboard import DashboardStatsSerializer
from vendor.permissions import IsVendor


# ... (other imports)
from django.db.models import Avg, Sum, Count, Q, F, Case, When, DecimalField


from vendor.models import Vendor
from store.models import Product, CartOrder, Review



# Imports for Swagger Schema Documentation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


application_logger = logging.getLogger('application')






class DashboardStatsAPIView(generics.GenericAPIView):
    """
    API endpoint to retrieve the aggregated statistics for the main vendor dashboard.

    This view is architected for maximum performance and scalability by leveraging
    Django's reverse relationship managers. It ensures that all data is fetched
    starting from the vendor object, providing clean, object-oriented, and highly
    optimized database queries.

    *   **URL:** `/api/vendor/dashboard/stats/`
    *   **Method:** `GET`
    *   **Authentication:** `IsAuthenticated`
    *   **Permissions:** `IsVendor`
    """
    permission_classes = [IsAuthenticated, IsVendor]
    serializer_class = DashboardStatsSerializer

    @swagger_auto_schema(
        operation_summary="Get Vendor Dashboard Statistics (Reverse Lookup Optimized)",
        operation_description="Fetches all necessary KPIs for the main vendor dashboard using an advanced, reverse-lookup query strategy for elite performance and scalability.",
        responses={
            200: openapi.Response("Dashboard statistics retrieved successfully", DashboardStatsSerializer),
            403: "Permission Denied - User is not an authorized vendor",
            404: "Not Found - Vendor profile is missing",
            500: "Internal Server Error"
        }
    )
    def get(self, request, *args, **kwargs):
        """
        Handles the GET request to compile and return dashboard statistics.

        This method begins with the authenticated vendor instance and traverses its
        reverse relationships (`vendor_product_set`, `cartorder_vendor`) to perform
        all necessary aggregations in a minimal number of database calls.
        """
        user = request.user
        application_logger.info(f"Dashboard stats requested by user: {user.identifying_info}")

        try:
            # The IsVendor permission class ensures request.user.vendor_profile exists.
            vendor = request.user.vendor_profile

            # --- ADVANCED ORM REVERSE LOOKUP STRATEGY ---
            # All queries now originate from the 'vendor' object instance.

            # === Query 1: Aggregating through the Product relationship ===
            # We use `vendor.vendor_product_set` (the related_name for Products) to get
            # both product counts and review statistics in a single, efficient query.
            product_and_review_stats = vendor.vendor_product_set.aggregate(
                # Count out-of-stock products belonging to this vendor.
                out_of_stock_count=Count('id', filter=Q(in_stock=False)),
                # Calculate average rating by traversing from Product -> Review.
                store_review_average=Avg('review_product__rating'),
                # Count total reviews by traversing from Product -> Review.
                store_review_count=Count('review_product')
            )

            # === Query 2: Aggregating through the CartOrder relationship ===
            # We use `vendor.cartorder_vendor` (the related_name for CartOrders)
            # to calculate all financial and order-related metrics.
            order_stats = vendor.cartorder_vendor.aggregate(
                # Sum the total of 'paid' orders.
                sales_total=Sum('total', filter=Q(payment_status="paid")),
                # Average the total of 'Fulfilled' orders.
                average_order_value=Avg('total', filter=Q(order_status="Fulfilled")),
                # Count all 'unfulfilled' orders.
                unfulfilled_orders_count=Count('id', filter=Q(order_status__in=['Pending', 'Partially Fulfilled', 'Processing']))
            )

            # --- Prepare Data for Serialization ---
            # Assemble the final data dictionary from our two optimized queries.
            # Using .get() with a default value ensures robustness if a vendor has no data.
            data = {
                'store_review_average': product_and_review_stats.get('store_review_average') or 0.0,
                'store_review_count': product_and_review_stats.get('store_review_count') or 0,
                'average_order_value': order_stats.get('average_order_value') or 0.0,
                'out_of_stock_count': product_and_review_stats.get('out_of_stock_count') or 0,
                'unfulfilled_orders_count': order_stats.get('unfulfilled_orders_count') or 0,
                'sales_total': order_stats.get('sales_total') or 0.0,
            }

            serializer = self.get_serializer(data)

            application_logger.info(f"Successfully compiled dashboard stats for vendor '{vendor.name}' using advanced reverse-lookup strategy.")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Vendor.DoesNotExist:
            # This critical error indicates a data integrity issue (a vendor user without a profile).
            application_logger.critical(f"CRITICAL: User {user.email} with 'vendor' role has no Vendor profile.")
            return Response({"error": "Vendor profile not found. Please contact support."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # A final, robust catch-all for any other unexpected server-side issues.
            application_logger.critical(f"An unexpected server error occurred while generating dashboard stats for {user.identifying_info}: {str(e)}")
            return Response({"error": "An unexpected server error occurred. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

































