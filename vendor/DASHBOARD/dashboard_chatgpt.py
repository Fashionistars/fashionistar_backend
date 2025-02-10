from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils.html import mark_safe
from userauths.models import User, user_directory_path
from django.utils.text import slugify
import shortuuid
from django.db.models import Avg
import uuid
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.postgres.fields import ArrayField

class Vendor(models.Model):
    """
    Represents a Vendor in the e-commerce platform.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="vendor_profile")
    image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg",null=True, blank=True)
    name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
    email = models.EmailField(max_length=100, help_text="Shop Email", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    mobile = models.CharField(max_length=150, null=True, blank=True)
    verified = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    vid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    date = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(blank=True, null=True)
    transaction_password = models.CharField(max_length=128, blank=True, null=True, help_text="Hashed transaction password. Must be a 4-digit number when set.")


    # Business Hours
    opening_time = models.TimeField(blank=True, null=True, help_text="Opening time")
    closing_time = models.TimeField(blank=True, null=True, help_text="Closing time")
    # Using ArrayField for multiple days/hours
    business_hours = ArrayField(models.CharField(max_length=50), blank=True, null=True, help_text="e.g., ['Monday: 9 AM - 5 PM', 'Tuesday: 9 AM - 5 PM']")




    class Meta:
        verbose_name_plural = "Vendors"

    def vendor_image(self):
        """
        Returns an HTML image tag for the vendor's image, used in Django Admin.
        """
        return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        """
        Returns the string representation of the vendor (shop name).
        """
        return str(self.name)

    def save(self, *args, **kwargs):
        """
        Overrides the save method to auto-generate a slug if one doesn't already exist.
        """
        if self.slug == "" or self.slug is None:
            uuid_key = shortuuid.uuid()
            uniqueid = uuid_key[:4]
            self.slug = slugify(self.name.lower()) + "-" + str(uniqueid.lower())

        # Ensure the instance is saved to the database after modifying fields like 'slug'
        super().save(*args, **kwargs)

    def get_average_rating(self):
        """
        Calculates and returns the average rating for the products of this vendor.
        """
        return self.vendor_role.aggregate(average_rating=Avg('rating')).get('average_rating', 0)

    def set_transaction_password(self, password):
         """
        Hashes the given transaction password using bcrypt and stores it securely in the database.

        Args:
            password (str): The plain transaction password to be hashed.
         """
        self.transaction_password = make_password(password)
        self.save()

    def check_transaction_password(self, password):
        """
        Verifies the given transaction password against the stored hashed password.

        Args:
            password (str): The plain transaction password to be verified.

        Returns:
            bool: True if the password matches, False otherwise.
        """
        return check_password(password, self.transaction_password)
    
    def get_wallet_balance(self):
        """
        Retrieves the total wallet balance for the vendor.
        """
        return WalletTransaction.objects.filter(vendor=self).aggregate(total_balance=Sum('amount'))['total_balance'] or 0

    def get_pending_payouts(self):
        """
        Calculates the total pending payouts for the vendor.
        """
        return CartOrder.objects.filter(vendor=self, payment_status='pending').aggregate(total_pending=Sum('total'))['total_pending'] or 0

    def get_order_status_counts(self):
        """
        Retrieves the counts of orders for each status associated with the vendor.
        """
        return CartOrder.objects.filter(vendor=self).values('payment_status').annotate(count=Count('id'))

    def get_top_selling_products(self, limit=5):
        """
        Retrieves the top-selling products for the vendor, limited to the specified number.

        Args:
            limit (int): The maximum number of top-selling products to return.

        Returns:
            QuerySet: A queryset containing the top-selling products ordered by sales.
        """
        return Product.objects.filter(vendor=self).annotate(total_sales=Sum('cartorderitem__qty')).order_by('-total_sales')[:limit]

    def get_revenue_trends(self, months=6):
        """
        Retrieves revenue trends for the vendor over the specified number of months.

        Args:
            months (int): The number of months to retrieve revenue trends for.

        Returns:
            QuerySet: A queryset containing revenue trends data grouped by month.
        """
        six_months_ago = datetime.now() - timedelta(days=months * 30)  # Approximation for months
        return CartOrder.objects.filter(vendor=self, payment_status='paid', date__gte=six_months_ago) \
            .annotate(month=ExtractMonth('date')).values('month').annotate(total_revenue=Sum('total'))

    def get_customer_behavior(self):
        """
        Retrieves customer behavior data for the vendor, grouped by hour.
        """
        return CartOrder.objects.filter(vendor=self, payment_status='paid') \
            .annotate(hour=F('date__hour')).values('hour').annotate(order_count=Count('id'))

    def get_low_stock_alerts(self, threshold=5):
        """
        Retrieves products with stock levels below the specified threshold.

        Args:
            threshold (int): The stock level threshold.

        Returns:
            QuerySet: A queryset containing products with low stock.
        """
        return Product.objects.filter(vendor=self, stock_qty__lt=threshold).values('title', 'stock_qty')

    def get_review_count(self):
        """
        Retrieves the count of reviews associated with the vendor's products.
        """
        return Review.objects.filter(product__vendor=self).count()

    def get_average_review_rating(self):
        """
        Retrieves the average review rating for the vendor's products.
        """
        return Review.objects.filter(product__vendor=self).aggregate(avg_rating=Avg('rating'))['avg_rating'] or 0

    def get_coupon_data(self):
        """
        Retrieves coupon data for the vendor.
        """
        return Coupon.objects.filter(vendor=self).values('code', 'discount', 'date')

    def get_abandoned_carts(self):
        """
        Retrieves abandoned carts for the vendor (carts with 'pending' payment status).
        """
        return CartOrder.objects.filter(vendor=self, payment_status='pending').values('buyer__email', 'total')

    def calculate_average_order_value(self):
        """
        Calculates the average order value for the vendor's fulfilled orders.
        """
        return CartOrder.objects.filter(vendor=self, payment_status="Fulfilled").aggregate(avg_order_value=Avg('total'))['avg_order_value'] or 0

    def calculate_total_sales(self):
        """
        Calculates the total sales amount for the vendor's paid orders.
        """
        return CartOrder.objects.filter(vendor=self, payment_status="paid").aggregate(total_sales=Sum('total'))['total_sales'] or 0
    

























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