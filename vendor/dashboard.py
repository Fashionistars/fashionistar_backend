from django.db.models import Avg, Sum, F, Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import logging
from django.db.models.functions import ExtractMonth

from vendor.utils import fetch_user_and_vendor  # Removed now
from store.models import CartOrderItem, CartOrder, Product, Review, Coupon
from vendor.models import Vendor, WalletTransaction
from datetime import datetime, timedelta

# Serializers
from userauths.serializer import ProfileSerializer
from store.serializers import CouponSummarySerializer, EarningSummarySerializer, SummarySerializer, CartOrderItemSerializer, ProductSerializer, CartOrderSerializer, GallerySerializer, ReviewSerializer, SpecificationSerializer, CouponSerializer, ColorSerializer, SizeSerializer, VendorSerializer
from vendor.serializers import *

# Models
from userauths.models import Profile, User

# Custom Permissions
from vendor.permissions import IsVendor, VendorIsOwner  # Import custom permissions

application_logger = logging.getLogger('application')

class VendorDashboardAPIView(generics.ListAPIView):
    """
    API endpoint to retrieve comprehensive vendor dashboard statistics.
    """
    permission_classes = [IsAuthenticated, IsVendor]  # Apply permissions

    def get_dashboard_data(self, vendor):
        """Fetch all essential vendor dashboard data."""
        return {
            'wallet_balance': vendor.get_wallet_balance(),
            'pending_payouts': vendor.get_pending_payouts(),
            'orders': vendor.get_order_status_counts(),
            'top_selling_products': self.serialize_top_selling_products(vendor.get_top_selling_products()),
            'revenue_trends': list(vendor.get_revenue_trends()),
            'customer_behavior': list(vendor.get_customer_behavior()),
            'low_stock_alerts': list(vendor.get_low_stock_alerts()),
            'review_count': vendor.get_review_count(),
            'average_review': vendor.get_average_review_rating(),
            'coupons': list(vendor.get_coupon_data()),
            'abandoned_carts': list(vendor.get_abandoned_carts()),
            'average_order_value': vendor.calculate_average_order_value(),
            'total_sales': vendor.calculate_total_sales(),
            'user_image': vendor.image.url if vendor.image else "",
            'total_products': vendor.get_total_products(),
            'active_coupons': vendor.get_active_coupons(),
            'inactive_coupons': vendor.get_inactive_coupons(),
            'total_customers': vendor.get_total_customers(),
            'todays_sales': vendor.get_todays_sales(),
            'this_month_sales': vendor.get_this_month_sales(),
            'year_to_date_sales': vendor.get_year_to_date_sales(),
            'new_customers_this_month': vendor.get_new_customers_this_month(),
            'top_performing_categories': vendor.get_top_performing_categories(),
            'payment_method_distribution': vendor.get_payment_method_distribution(),
        }

    def serialize_top_selling_products(self, products):
        """
        Serializes the top-selling products.

        Args:
            products (QuerySet): A queryset of top-selling products.

        Returns:
            list: A list of serialized top-selling products.
        """
        return ProductSerializer(products, many=True).data

    def list(self, request, *args, **kwargs):
        """
        List serialized dashboard data.
        """
        try:
            user = request.user  # Get the authenticated user

            # Try to get the vendor profile
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
                application_logger.error(f"Vendor profile not found for user: {user.email}")
                return Response({'error': 'Vendor profile not found'}, status=status.HTTP_404_NOT_FOUND)

            data = self.get_dashboard_data(vendor)
            return Response(data)

        except Exception as e:
            # Catch any unexpected exceptions and log them
            application_logger.error(f"Unexpected error: {e}")
            # Return a generic error message to the client
            return Response({'error': 'An unexpected error occurred. Please contact support.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


























# from django.db.models import Avg, Sum, F, Count
# from rest_framework import generics, status
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# import logging
# from django.db.models.functions import ExtractMonth
# from django.utils import timezone

# from store.models import CartOrderItem, CartOrder, Product, Review, Coupon
# from vendor.models import Vendor, WalletTransaction
# from datetime import datetime, timedelta

# # Serializers
# from userauths.serializer import ProfileSerializer
# from store.serializers import CouponSummarySerializer, EarningSummarySerializer, SummarySerializer, CartOrderItemSerializer, ProductSerializer, CartOrderSerializer, GallerySerializer, ReviewSerializer, SpecificationSerializer, CouponSerializer, ColorSerializer, SizeSerializer, VendorSerializer
# from vendor.serializers import *

# # Models
# from userauths.models import Profile, User

# # Custom Permissions
# from vendor.permissions import IsVendor  # Import custom permissions

# application_logger = logging.getLogger('application')

# class VendorDashboardAPIView(generics.ListAPIView):
#     """
#     API endpoint to retrieve comprehensive vendor dashboard statistics.
#     """
#     permission_classes = [IsAuthenticated, IsVendor]  # Apply permissions

#     def get_queryset(self):
#         """
#         Get the queryset of vendor summary data.
#         """
#         user = self.request.user
#         try:
#             # Use select_related to optimize the query
#             return Vendor.objects.filter(user=user).select_related('user')
#         except Exception as e:
#             application_logger.error(f"Error retrieving vendor dashboard: {e}")
#             return Response({'error': f'Error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#     def get_dashboard_data(self, vendor):
#         """Fetch all essential vendor dashboard data."""
#         return {
#             'wallet_balance': vendor.get_wallet_balance(),
#             'pending_payouts': vendor.get_pending_payouts(),
#             'orders': vendor.get_order_status_counts(),
#             'top_selling_products': self.serialize_top_selling_products(vendor.get_top_selling_products()),
#             'revenue_trends': list(vendor.get_revenue_trends()),
#             'customer_behavior': list(vendor.get_customer_behavior()),
#             'low_stock_alerts': list(vendor.get_low_stock_alerts()),
#             'review_count': vendor.get_review_count(),
#             'average_review': vendor.get_average_review_rating(),
#             'coupons': list(vendor.get_coupon_data()),
#             'abandoned_carts': list(vendor.get_abandoned_carts()),
#             'average_order_value': vendor.calculate_average_order_value(),
#             'total_sales': vendor.calculate_total_sales(),
#             'user_image': vendor.image.url if vendor.image else "",

#             # ADDED DATA QUERIED FROM THE DB
#             'total_products': vendor.get_total_products(),
#             'active_coupons': vendor.get_active_coupons(),
#             'inactive_coupons': vendor.get_inactive_coupons(),
#             'total_customers': vendor.get_total_customers(),
#             'todays_sales': vendor.get_todays_sales(),
#             'this_month_sales': vendor.get_this_month_sales(),
#             'year_to_date_sales': vendor.get_year_to_date_sales(),
#             'new_customers_this_month': vendor.get_new_customers_this_month(),
#             'top_performing_categories': vendor.get_top_performing_categories(),
#             'payment_method_distribution': vendor.get_payment_method_distribution(),
#         }

#     def serialize_top_selling_products(self, products):
#         """
#         Serializes the top-selling products.

#         Args:
#             products (QuerySet): A queryset of top-selling products.

#         Returns:
#             list: A list of serialized top-selling products.
#         """
#         return ProductSerializer(products, many=True).data

#     def list(self, request, *args, **kwargs):
#         """
#         List serialized dashboard data.
#         """
#         try:
#             queryset = self.get_queryset()
#             vendor = queryset.first()

#             if not vendor:
#                 return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)

#             data = self.get_dashboard_data(vendor)
#             return Response(data)

#         except Exception as e:
#             application_logger.error(f"Unexpected error: {e}")
#             return Response({'error': 'An unexpected error occurred. Please contact support.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
















































































































                            
# ====================== SIDE WITH DOC STRING COMMENT================

















# application_logger = logging.getLogger('application')


# class VendorDashboardAPIView(generics.ListAPIView):
#     """
#     API endpoint to retrieve comprehensive vendor dashboard statistics.
#     """
#     """
#     API endpoint to retrieve dashboard statistics for a vendor.
#     *   *URL:* /api/vendor/dashboard/
#     *   *Method:* GET
#     *   *Authentication:* Requires a valid authentication token in the Authorization header.
#     *   *Request Body:* None
#         *   *Response (JSON):*
#                 *   On success (HTTP 200 OK):
#                     json
#                     {
#                     "out_of_stock": 2,
#                     "orders": 5,
#                     "revenue": 1500.00,
#                     "review": 3,
#                     "average_review": 4.2,
#                     "average_order_value": 500.00,
#                     "total_sales": 2500.00,
#                     "user_image": "http://example.com/media/shop-image.jpg"
#                     }
                    
#                 *   On failure (HTTP 400, 404 or 500):
#                     json
#                         {
#                             "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
#                         }
                
#                 Possible Error Messages:
#                 * "You do not have permission to perform this action.": If the user is not a vendor
#                 * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
#     """


#     permission_classes = [IsAuthenticated, IsVendor]  # Apply permissions

#     def get_dashboard_data(self, vendor):
#         """Fetch all essential vendor dashboard data."""
#         return {
#             'wallet_balance': vendor.get_wallet_balance(),
#             'pending_payouts': vendor.get_pending_payouts(),
#             'orders': vendor.get_order_status_counts(),
#             'top_selling_products': self.serialize_top_selling_products(vendor.get_top_selling_products()),
#             'revenue_trends': list(vendor.get_revenue_trends()),
#             'customer_behavior': list(vendor.get_customer_behavior()),
#             'low_stock_alerts': list(vendor.get_low_stock_alerts()),
#             'review_count': vendor.get_review_count(),
#             'average_review': vendor.get_average_review_rating(),
#             'coupons': list(vendor.get_coupon_data()),
#             'abandoned_carts': list(vendor.get_abandoned_carts()),
#             'average_order_value': vendor.calculate_average_order_value(),
#             'total_sales': vendor.calculate_total_sales(),
#             'user_image': vendor.image.url if vendor.image else "",
#             'total_products': vendor.get_total_products(),
#             'active_coupons': vendor.get_active_coupons(),
#             'inactive_coupons': vendor.get_inactive_coupons(),
#             'total_customers': vendor.get_total_customers(),
#             'todays_sales': vendor.get_todays_sales(),
#             'this_month_sales': vendor.get_this_month_sales(),
#             'year_to_date_sales': vendor.get_year_to_date_sales(),
#             'new_customers_this_month': vendor.get_new_customers_this_month(),
#             'top_performing_categories': vendor.get_top_performing_categories(),
#             'payment_method_distribution': vendor.get_payment_method_distribution(),
#         }

#     def serialize_top_selling_products(self, products):
#         """
#         Serializes the top-selling products.

#         Args:
#             products (QuerySet): A queryset of top-selling products.

#         Returns:
#             list: A list of serialized top-selling products.
#         """
#         return ProductSerializer(products, many=True).data

#     def list(self, request, *args, **kwargs):
#         """
#         List serialized dashboard data.
#         """
#         try:
#             user = request.user  # Get the authenticated user

#             # Try to get the vendor profile
#             try:
#                 vendor = Vendor.objects.get(user=user)
#             except Vendor.DoesNotExist:
#                 application_logger.error(f"Vendor profile not found for user: {user.email}")
#                 return Response({'error': 'Vendor profile not found'}, status=status.HTTP_404_NOT_FOUND)

#             data = self.get_dashboard_data(vendor)
#             return Response(data)

#         except Exception as e:
#             # Catch any unexpected exceptions and log them
#             application_logger.error(f"Unexpected error: {e}")
#             # Return a generic error message to the client
#             return Response({'error': 'An unexpected error occurred. Please contact support.'},
#                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)











































