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

    def get_queryset(self):
        """
        Get the queryset of vendor summary data.
        """
        user = self.request.user
        try:
            # No need for custom validation
            return Vendor.objects.filter(user=user)
        except Exception as e:
            application_logger.error(f"Error retrieving vendor dashboard: {e}")
            return Response({'error': f'Error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            'user_image': vendor.image.url if vendor.image else ""
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
            queryset = self.get_queryset()
            vendor = queryset.first()
            if not vendor:
                return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)
            data = self.get_dashboard_data(vendor)
            return Response(data)
        except Exception as e:
            application_logger.error(f"Unexpected error: {e}")
            return Response({'error': 'An unexpected error occurred. Please contact support.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardStatsAPIView(generics.ListAPIView):
    """
    API endpoint to retrieve dashboard statistics for a vendor.
    """
    serializer_class = SummarySerializer
    permission_classes = [IsAuthenticated, IsVendor]  # Apply permissions

    def get_queryset(self):
        """
        Get the queryset of summary data for the dashboard stats.
        """
        user = self.request.user
        try:
            vendor = Vendor.objects.get(user=user)  # Get vendor object

            product_count = self.get_product_count(vendor)
            order_count = self.get_order_count(vendor)
            revenue = self.calculate_revenue(vendor)
            review_count = self.get_review_count(vendor)
            average_rating = self.calculate_average_rating(vendor)
            average_order_value = self.calculate_average_order_value(vendor)
            total_sales = self.calculate_total_sales(vendor)
            user_image = self.get_user_image(vendor)

            summary_object = {
                'out_of_stock': product_count,
                'orders': order_count,
                'revenue': revenue,
                'review': review_count,
                'average_review': average_rating,
                'average_order_value': average_order_value,
                'total_sales': total_sales,
                "user_image": user_image
            }
            return [summary_object]

        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor not found for user: {user.email}")
            return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving dashboard stats: {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_user_image(self, vendor):
        """
        Get the image of the vendor.
        """
        return vendor.image.url if vendor.image else ""

    def get_product_count(self, vendor):
        """
        Get the count of products associated with the vendor.
        """
        return Product.objects.filter(vendor=vendor, in_stock=False).count()

    def get_order_count(self, vendor):
        """
        Get the count of paid orders associated with the vendor.
        """
        return CartOrder.objects.filter(vendor=vendor, payment_status="paid").count()

    def calculate_revenue(self, vendor):
        """
        Calculate the total revenue generated by paid orders associated with the vendor.
        """
        total_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=Sum(F('sub_total') + F('shipping_amount')))['total_revenue'] or 0
        return total_revenue

    def get_review_count(self, vendor):
        """
        Get the count of reviews associated with products of the vendor.
        """
        vendor_product_ids = Product.objects.filter(vendor=vendor).values_list('id', flat=True)
        return Review.objects.filter(product_id__in=vendor_product_ids).count()

    def calculate_average_rating(self, vendor):
        """
        Calculate the average rating of products associated with the vendor.
        """
        vendor_product_ids = Product.objects.filter(vendor=vendor).values_list('id', flat=True)
        average_rating = Review.objects.filter(product_id__in=vendor_product_ids).aggregate(average=Avg('rating'))['average']
        if average_rating is None:
            average_rating = 0
        return average_rating

    def calculate_average_order_value(self, vendor):
        """
        Calculate the average order value of paid orders associated with the vendor.
        """
        average_order_value = CartOrder.objects.filter(vendor=vendor, payment_status="Fulfilled").aggregate(
            avg_order_value=Avg('total'))['avg_order_value'] or 0
        return average_order_value

    def calculate_total_sales(self, vendor):
        """
        Calculate the total sales (sum of all total amounts) of paid orders associated with the vendor.
        """
        total_sales = CartOrder.objects.filter(vendor=vendor, payment_status="paid").aggregate(
            total_sales=Sum('total'))['total_sales'] or 0
        return total_sales

    def list(self, request, *args, **kwargs):
        """
        Lists the serialized data.
        """
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving dashboard stats: {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)