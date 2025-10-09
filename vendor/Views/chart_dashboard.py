# vendor/Views/serializerss/chart_ashboard.py

import logging


from rest_framework import status
from rest_framework import generics
from rest_framework.response import Response

# ... (other imports)
from rest_framework.permissions import IsAuthenticated

# Import custom components from vendor app (adjusted for correct paths)
from vendor.serializerss.chart_dashboard import TotalOrdersChartSerializer, RevenueAnalyticsChartSerializer # Import new serializers
from vendor.permissions import IsVendor


# ... (other imports)
from django.db.models import Avg, Sum, Count, Q, F, Case, When, DecimalField
from django.db.models.functions import ExtractMonth


from vendor.models import Vendor
from store.models import Product, CartOrder, Review



# Imports for Swagger Schema Documentation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


application_logger = logging.getLogger('application')











class TotalOrdersChartAPIView(generics.GenericAPIView):
    """
    API endpoint to provide data for the "Total Orders" chart on the dashboard.

    This view aggregates the total number of orders per month for the authenticated
    vendor, using an optimized reverse-lookup query.

    *   **URL:** `/api/vendor/dashboard/charts/total-orders/`
    *   **Method:** `GET`
    *   **Authentication:** `IsAuthenticated`
    *   **Permissions:** `IsVendor`
    """
    permission_classes = [IsAuthenticated, IsVendor]
    serializer_class = TotalOrdersChartSerializer

    @swagger_auto_schema(
        operation_summary="Get Data for Total Orders Chart",
        operation_description="Fetches a list of data points, with each point representing the total count of orders for a given month.",
        responses={200: TotalOrdersChartSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        """
        Handles the GET request to compile and return the Total Orders chart data.
        """
        user = request.user
        application_logger.info(f"Total Orders chart data requested by user: {user.identifying_info}")

        try:
            vendor = request.user.vendor_profile

            # === ADVANCED ORM REVERSE LOOKUP STRATEGY ===
            # Query starts from the vendor and traverses to its related orders.
            chart_data = vendor.cartorder_vendor.annotate(
                month=ExtractMonth("date")  # Extract the month number from the order date.
            ).values(
                "month"  # Group by the extracted month.
            ).annotate(
                orders_count=Count("id")  # Count the number of orders in each group.
            ).order_by(
                "month"  # Order the results by month.
            )

            serializer = self.get_serializer(chart_data, many=True)
            application_logger.info(f"Successfully compiled Total Orders chart data for vendor: {vendor.name}")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Vendor.DoesNotExist:
            application_logger.critical(f"CRITICAL: User {user.email} with 'vendor' role has no Vendor profile.")
            return Response({"error": "Vendor profile not found. Please contact support."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            application_logger.critical(f"An unexpected error occurred while generating Total Orders chart data for {user.identifying_info}: {str(e)}")
            return Response({"error": "An unexpected server error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RevenueAnalyticsChartAPIView(generics.GenericAPIView):
    """
    API endpoint to provide data for the "Revenue Analytics" chart on the dashboard.

    This view aggregates the total revenue from 'paid' order items per month for the
    authenticated vendor, using an optimized reverse-lookup query.

    *   **URL:** `/api/vendor/dashboard/charts/revenue-analytics/`
    *   **Method:** `GET`
    *   **Authentication:** `IsAuthenticated`
    *   **Permissions:** `IsVendor`
    """
    permission_classes = [IsAuthenticated, IsVendor]
    serializer_class = RevenueAnalyticsChartSerializer

    @swagger_auto_schema(
        operation_summary="Get Data for Revenue Analytics Chart",
        operation_description="Fetches a list of data points, with each point representing the total revenue for a given month.",
        responses={200: RevenueAnalyticsChartSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        """
        Handles the GET request to compile and return the Revenue Analytics chart data.
        """
        user = request.user
        application_logger.info(f"Revenue Analytics chart data requested by user: {user.identifying_info}")

        try:
            vendor = request.user.vendor_profile

            # === ADVANCED ORM REVERSE LOOKUP STRATEGY ===
            # We query through `CartOrderItem` for revenue accuracy, starting from the vendor.
            # The related_name from CartOrderItem -> Vendor is 'order_item_vendor'.
            chart_data = vendor.order_item_vendor.filter(
                order__payment_status="paid"  # Only include items from paid orders.
            ).annotate(
                month=ExtractMonth("date")
            ).values(
                "month"
            ).annotate(
                # Sum the total for each item to get the monthly revenue.
                total_revenue=Sum('total')
            ).order_by(
                "month"
            )

            serializer = self.get_serializer(chart_data, many=True)
            application_logger.info(f"Successfully compiled Revenue Analytics chart data for vendor: {vendor.name}")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Vendor.DoesNotExist:
            application_logger.critical(f"CRITICAL: User {user.email} with 'vendor' role has no Vendor profile.")
            return Response({"error": "Vendor profile not found. Please contact support."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            application_logger.critical(f"An unexpected error occurred while generating Revenue Analytics chart data for {user.identifying_info}: {str(e)}")
            return Response({"error": "An unexpected server error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


