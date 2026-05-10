from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils.html import mark_safe
from Paystack_Webhoook_Prod.models import WalletTransaction
from userauths.models import User, user_directory_path
from django.utils.text import slugify
import shortuuid
from django.db.models import Avg, Sum, F, Count
import uuid
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.postgres.fields import ArrayField
from datetime import datetime, timedelta
from django.db.models.functions import ExtractMonth
from django.utils import timezone  # IMPORT THE TIMEZONE
from django.db.models import Q  # IMPORT Q LOOKUP IN ORDER TO PROVIDE ROBUST SEARCH FILTER ACCORDINGLY
import logging

# No direct imports from store.models anymore!

application_logger = logging.getLogger('application')


class Vendor(models.Model):
    """
    Represents a Vendor in the e-commerce platform.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="vendor_profile",
                                 db_index=True)  # Index user
    image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg", null=True, blank=True)
    name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
    email = models.EmailField(max_length=100, help_text="Shop Email", null=True, blank=True, db_index=True)  # Index email
    description = models.TextField(null=True, blank=True)
    mobile = models.CharField(max_length=150, null=True, blank=True)
    verified = models.BooleanField(default=True, db_index=True)  # Index verified
    active = models.BooleanField(default=True, db_index=True)  # Index active
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    vid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
    date = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(blank=True, null=True, db_index=True)  # Index slug
    transaction_password = models.CharField(max_length=128, blank=True, null=True,
                                            help_text="Hashed transaction password. Must be a 4-digit number when set.")

    # Business Hours
    opening_time = models.TimeField(blank=True, null=True, help_text="Opening time")
    closing_time = models.TimeField(blank=True, null=True, help_text="Closing time")
    # # Using ArrayField for multiple days/hours   ========== TO BE USED ONCE WE SWITH TO USE POSTGRES DATABASE IN THE FUTURE ==================
    # business_hours = ArrayField(models.CharField(max_length=50), blank=True, null=True,
    #                              help_text="e.g., ['Monday: 9 AM - 5 PM', 'Tuesday: 9 AM - 5 PM']")
    business_hours = models.JSONField(default=dict, blank=True, null=True, help_text="Store opening hours")
    
    class Meta:
        verbose_name_plural = "Vendors"
        indexes = [
            models.Index(fields=['name'], name='vendor_name_idx'),
            models.Index(fields=['slug'], name='vendor_slug_idx'),
            models.Index(fields=['user'], name='vendor_user_idx'),
        ]

    def vendor_image(self):
        """
        Returns an HTML image tag for the vendor's image, used in Django Admin.
        """
        return mark_safe(
            '  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (
                self.image.url))

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
        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products and calculates the average rating from their reviews.
        """
        return self.vendor_product_set.aggregate(average_rating=Avg('review_product__rating')).get('average_rating', 0)

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
        try:
            return WalletTransaction.objects.filter(vendor=self).aggregate(total_balance=Sum('amount'))[
                       'total_balance'] or 0
        except Exception as e:
            application_logger.error(f"Error getting wallet balance for vendor {self.name}: {e}")
            return 0

    def get_pending_payouts(self):
        """
        Calculates the total pending payouts for the vendor.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            return self.cartorder_vendor.filter(payment_status='pending').aggregate(
                total_pending=Sum('total'))['total_pending'] or 0
        except Exception as e:
            application_logger.error(f"Error getting pending payouts for vendor {self.name}: {e}")
            return 0

    def get_order_status_counts(self):
        """
        Retrieves the counts of orders for each status associated with the vendor.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            return self.cartorder_vendor.values('payment_status').annotate(count=Count('id'))
        except Exception as e:
            application_logger.error(f"Error getting order status counts for vendor {self.name}: {e}")
            return []

    def get_top_selling_products(self, limit=5):
        """
        Retrieves the top-selling products for the vendor, limited to the specified number.

        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products. It then annotates each product with the total quantity
        sold (using 'order_item_product__qty' from CartOrderItem) and orders them by sales.
        """
        try:
            return self.vendor_product_set.annotate(total_sales=Sum('order_item_product__qty')).order_by(
                '-total_sales')[:limit]
        except Exception as e:
            application_logger.error(f"Error getting top selling products for vendor {self.name}: {e}")
            return []

    def get_revenue_trends(self, months=6):
        """
        Retrieves revenue trends for the vendor over the specified number of months.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            six_months_ago = timezone.now() - timedelta(days=months * 30)  # Approximation for months
            return self.cartorder_vendor.filter(payment_status='paid', date__gte=six_months_ago) \
                .annotate(month=ExtractMonth('date')).values('month').annotate(total_revenue=Sum('total'))
        except Exception as e:
            application_logger.error(f"Error getting revenue trends for vendor {self.name}: {e}")
            return []

    def get_customer_behavior(self):
        """
        Retrieves customer behavior data for the vendor, grouped by hour.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            return self.cartorder_vendor.filter(payment_status='paid') \
                .annotate(hour=F('date__hour')).values('hour').annotate(order_count=Count('id'))
        except Exception as e:
            application_logger.error(f"Error getting customer behavior for vendor {self.name}: {e}")
            return []

    def get_low_stock_alerts(self, threshold=5):
        """
        Retrieves products with stock levels below the specified threshold.

        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products.
        """
        try:
            return self.vendor_product_set.filter(stock_qty__lt=threshold).values('title', 'stock_qty')
        except Exception as e:
            application_logger.error(f"Error getting low stock alerts for vendor {self.name}: {e}")
            return []

    def get_review_count(self):
        """
        Retrieves the count of reviews associated with the vendor's products.

        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products.
        """
        try:
            return self.vendor_product_set.count()
        except Exception as e:
            application_logger.error(f"Error getting review count for vendor {self.name}: {e}")
            return 0

    def get_average_review_rating(self):
        """
        Retrieves the average review rating for the vendor's products.

        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products and calculates the average rating from their reviews.
        """
        try:
            return self.vendor_product_set.aggregate(avg_rating=Avg('review_product__rating'))['avg_rating'] or 0
        except Exception as e:
            application_logger.error(f"Error getting average review rating for vendor {self.name}: {e}")
            return 0

    def get_coupon_data(self):
        """
        Retrieves coupon data for the vendor.

        Uses the 'coupon_vendor' related_name from the Coupon model
        to access coupons associated with this vendor.
        """
        try:
            return self.coupon_vendor.values('code', 'discount', 'date')
        except Exception as e:
            application_logger.error(f"Error getting coupon data for vendor {self.name}: {e}")
            return []

    def get_abandoned_carts(self):
        """
        Retrieves abandoned carts for the vendor (carts with 'pending' payment status).

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            return self.cartorder_vendor.filter(payment_status='pending').values('buyer__email', 'total')
        except Exception as e:
            application_logger.error(f"Error getting abandoned carts for vendor {self.name}: {e}")
            return []

    def calculate_average_order_value(self):
        """
        Calculates the average order value for the vendor's fulfilled orders.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            return self.cartorder_vendor.filter(payment_status="Fulfilled").aggregate(
                avg_order_value=Avg('total'))['avg_order_value'] or 0
        except Exception as e:
            application_logger.error(f"Error calculating average order value for vendor {self.name}: {e}")
            return 0

    def calculate_total_sales(self):
        """
        Calculates the total sales amount for the vendor's paid orders.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            return self.cartorder_vendor.filter(payment_status="paid").aggregate(
                total_sales=Sum('total'))['total_sales'] or 0
        except Exception as e:
            application_logger.error(f"Error calculating total sales for vendor {self.name}: {e}")
            return 0

    def get_total_products(self):
        """
        Get the total count of products associated with a given vendor.

        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products.
        """
        try:
            # Count all products associated with the vendor to get the total products.
            total_products = self.vendor_product_set.count()
            return total_products
        except Exception as e:
            application_logger.error(f"Error getting total products for vendor {self.name}: {e}")
            return 0

    def get_active_coupons(self):
        """
        Get the count of active coupons for a given vendor.

        Uses the 'coupon_vendor' related_name from the Coupon model
        to access coupons associated with this vendor.
        """
        try:
            # Count all active coupons associated with the vendor.
            active_coupons = self.coupon_vendor.filter(active=True).count()
            return active_coupons
        except Exception as e:
            application_logger.error(f"Error getting active coupons for vendor {self.name}: {e}")
            return 0

    def get_inactive_coupons(self):
        """
        Get the count of inactive coupons for a given vendor.

        Uses the 'coupon_vendor' related_name from the Coupon model
        to access coupons associated with this vendor.
        """
        try:
            # Count all inactive coupons associated with the vendor.
            inactive_coupons = self.coupon_vendor.filter(active=False).count()
            return inactive_coupons
        except Exception as e:
            application_logger.error(f"Error getting inactive coupons for vendor {self.name}: {e}")
            return 0

    def get_total_customers(self):
        """
        Get the total count of unique customers who have placed orders with a given vendor.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            # Count the unique buyers associated with cart orders for the vendor.
            total_customers = self.cartorder_vendor.values('buyer').distinct().count()
            return total_customers
        except Exception as e:
            application_logger.error(f"Error getting total customers for vendor {self.name}: {e}")
            return 0

    def get_todays_sales(self):
        """
        Calculate the total sales for a given vendor for today.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            # Calculate the sum of all order totals for the vendor where payment status is "paid" and the order was created today.
            today = timezone.now().date()
            todays_sales = self.cartorder_vendor.filter(payment_status="paid", date__date=today).aggregate(
                total_sales=Sum('total'))['total_sales'] or 0
            return todays_sales
        except Exception as e:
            application_logger.error(f"Error getting today's sales for vendor {self.name}: {e}")
            return 0

    def get_this_month_sales(self):
        """
        Calculate the total sales for a given vendor for the current month.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            # Calculate the sum of all order totals for the vendor where payment status is "paid" and the order was created in the current month.
            now = timezone.now()
            this_month_sales = self.cartorder_vendor.filter(payment_status="paid", date__month=now.month,
                                                         date__year=now.year).aggregate(total_sales=Sum('total'))[
                                   'total_sales'] or 0
            return this_month_sales
        except Exception as e:
            application_logger.error(f"Error getting this month's sales for vendor {self.name}: {e}")
            return 0

    def get_year_to_date_sales(self):
        """
        Calculate the total sales for a given vendor for the year to date.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            # Calculate the sum of all order totals for the vendor where payment status is "paid" and the order was created in the current year.
            now = timezone.now()
            year_to_date_sales = self.cartorder_vendor.filter(payment_status="paid", date__year=now.year).aggregate(
                total_sales=Sum('total'))['total_sales'] or 0
            return year_to_date_sales
        except Exception as e:
            application_logger.error(f"Error getting year-to-date sales for vendor {self.name}: {e}")
            return 0

    def get_new_customers_this_month(self):
        """
        Get the count of new customers for a given vendor for the current month.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            # Count the unique buyers who placed their first order with the vendor in the current month.
            now = timezone.now()
            # Retrieve all customers for the current vendor and month
            customers = self.cartorder_vendor.filter(date__month=now.month, date__year=now.year).values(
                'buyer')

            # Determine the number of these customers who have only made one order this month
            new_customers_this_month = 0
            for customer in customers:
                customer_order_count = self.cartorder_vendor.filter(buyer=customer['buyer'], date__month=now.month,
                                                                 date__year=now.year).count()
                if customer_order_count == 1:
                    new_customers_this_month += 1
            return new_customers_this_month
        except Exception as e:
            application_logger.error(f"Error getting new customers this month for vendor {self.name}: {e}")
            return 0

    def get_top_performing_categories(self):
        """
        Get the top-performing product categories for a given vendor based on sales revenue.

        Uses the 'vendor_product_set' related_name from the Product model
        to access the vendor's products. Then aggregates sales based on 'order_item_product__total', which
        traverses the relationship from Product -> CartOrderItem to get the total revenue per category.
        """
        try:
            # Retrieve the top-performing categories based on the sum of order totals for products in each category.

            top_categories = self.vendor_product_set.values('category__name').annotate(
                sales=Sum('order_item_product__total')).order_by('-sales')[:5]
            return list(top_categories)
        except Exception as e:
            application_logger.error(f"Error getting top-performing categories for vendor {self.name}: {e}")
            return []

    def get_payment_method_distribution(self):
        """
        Get the distribution of payment methods used by customers for a given vendor.

        Uses the 'cartorder_vendor' related_name from the CartOrder model
        to access cart orders associated with this vendor.
        """
        try:
            # payment_method_distribution = CartOrder.objects.filter(vendor=vendor).values('payment_method').annotate(count=Count('id'))
            # return list(payment_method_distribution)

            # Aggregate the total amount associated with each method
            payment_methods = self.cartorder_vendor.values('payment_status').annotate(total=Sum('total'))
            # Calculate the percentage distribution
            total_revenue = sum(method['total'] for method in payment_methods)
            payment_distribution = []

            if total_revenue > 0:
                for method in payment_methods:
                    percentage = (method['total'] / total_revenue) * 100
                    payment_distribution.append({
                        'payment_method': method['payment_status'],
                        'percentage': round(percentage, 2)
                    })
            return payment_distribution
        except Exception as e:
            application_logger.error(f"Error getting payment method distribution for vendor {self.name}: {e}")
            return []




















































































# ============================================    ============================================    

#  TO BE LEARNT FROM LATER HOW TO USE REVERSE QUERY FOR GETTING EXACT ITEM MATCH FROM A FOREIG_KEY RELATED MODEL RELATED TO A PARTICULAR VENDOR / OTHER MODELS 

# ====================================================================================================================================================================
# ====================================================================================================================================================================


























# from django.db import models
# from shortuuid.django_fields import ShortUUIDField
# from django.utils.html import mark_safe
# from userauths.models import User, user_directory_path
# from django.utils.text import slugify
# import shortuuid
# from django.db.models import Avg, Sum, F, Count
# import uuid
# from django.contrib.auth.hashers import make_password, check_password
# from django.contrib.postgres.fields import ArrayField
# from datetime import datetime, timedelta
# from django.db.models.functions import ExtractMonth
# from django.utils import timezone  # IMPORT THE TIMEZONE
# from django.db.models import Q  # IMPORT Q LOOKUP IN ORDER TO PROVIDE ROBUST SEARCH FILTER ACCORDINGLY
# import logging

# # Import models used by vendor app, but declared in store app to avoid circular dependency
# from store.models import CartOrderItem, CartOrder, Product, Review, Coupon


# application_logger = logging.getLogger('application')


# class Vendor(models.Model):
#     """
#     Represents a Vendor in the e-commerce platform.
#     """
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="vendor_profile", db_index=True)  # Index user
#     image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg", null=True, blank=True)
#     name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
#     email = models.EmailField(max_length=100, help_text="Shop Email", null=True, blank=True, db_index=True)  # Index email
#     description = models.TextField(null=True, blank=True)
#     mobile = models.CharField(max_length=150, null=True, blank=True)
#     verified = models.BooleanField(default=True, db_index=True)  # Index verified
#     active = models.BooleanField(default=True, db_index=True)  # Index active
#     wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
#     vid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")
#     date = models.DateTimeField(auto_now_add=True)
#     slug = models.SlugField(blank=True, null=True, db_index=True)  # Index slug
#     transaction_password = models.CharField(max_length=128, blank=True, null=True,
#                                             help_text="Hashed transaction password. Must be a 4-digit number when set.")

#     # Business Hours
#     opening_time = models.TimeField(blank=True, null=True, help_text="Opening time")
#     closing_time = models.TimeField(blank=True, null=True, help_text="Closing time")
#     # Using ArrayField for multiple days/hours
#     business_hours = ArrayField(models.CharField(max_length=50), blank=True, null=True,
#                                  help_text="e.g., ['Monday: 9 AM - 5 PM', 'Tuesday: 9 AM - 5 PM']")

#     class Meta:
#         verbose_name_plural = "Vendors"
#         indexes = [
#             models.Index(fields=['name'], name='vendor_name_idx'),
#             models.Index(fields=['slug'], name='vendor_slug_idx'),
#             models.Index(fields=['user'], name='vendor_user_idx'),
#         ]

#     def vendor_image(self):
#         """
#         Returns an HTML image tag for the vendor's image, used in Django Admin.
#         """
#         return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

#     def __str__(self):
#         """
#         Returns the string representation of the vendor (shop name).
#         """
#         return str(self.name)

#     def save(self, *args, **kwargs):
#         """
#         Overrides the save method to auto-generate a slug if one doesn't already exist.
#         """
#         if self.slug == "" or self.slug is None:
#             uuid_key = shortuuid.uuid()
#             uniqueid = uuid_key[:4]
#             self.slug = slugify(self.name.lower()) + "-" + str(uniqueid.lower())

#         # Ensure the instance is saved to the database after modifying fields like 'slug'
#         super().save(*args, **kwargs)

#     def get_average_rating(self):
#         """
#         Calculates and returns the average rating for the products of this vendor.
#         """
#         return self.vendor_product_set.aggregate(average_rating=Avg('rating')).get('average_rating', 0)

#     def set_transaction_password(self, password):
#         """
#         Hashes the given transaction password using bcrypt and stores it securely in the database.

#         Args:
#             password (str): The plain transaction password to be hashed.
#          """
#         self.transaction_password = make_password(password)
#         self.save()

#     def check_transaction_password(self, password):
#         """
#         Verifies the given transaction password against the stored hashed password.

#         Args:
#             password (str): The plain transaction password to be verified.

#         Returns:
#             bool: True if the password matches, False otherwise.
#         """
#         return check_password(password, self.transaction_password)

#     def get_wallet_balance(self):
#         """
#         Retrieves the total wallet balance for the vendor.
#         """
#         try:
#             return WalletTransaction.objects.filter(vendor=self).aggregate(total_balance=Sum('amount'))[
#                        'total_balance'] or 0
#         except Exception as e:
#             application_logger.error(f"Error getting wallet balance for vendor {self.name}: {e}")
#             return 0

#     def get_pending_payouts(self):
#         """
#         Calculates the total pending payouts for the vendor.
#         """
#         try:
#             return CartOrder.objects.filter(vendor=self, payment_status='pending').aggregate(
#                 total_pending=Sum('total'))['total_pending'] or 0
#         except Exception as e:
#             application_logger.error(f"Error getting pending payouts for vendor {self.name}: {e}")
#             return 0

#     def get_order_status_counts(self):
#         """
#         Retrieves the counts of orders for each status associated with the vendor.
#         """
#         try:
#             return CartOrder.objects.filter(vendor=self).values('payment_status').annotate(count=Count('id'))
#         except Exception as e:
#             application_logger.error(f"Error getting order status counts for vendor {self.name}: {e}")
#             return []

#     def get_top_selling_products(self, limit=5):
#         """
#         Retrieves the top-selling products for the vendor, limited to the specified number.

#         Args:
#             limit (int): The maximum number of top-selling products to return.

#         Returns:
#             QuerySet: A queryset containing the top-selling products ordered by sales.
#         """
#         try:
#             return Product.objects.filter(vendor=self).annotate(total_sales=Sum('cartorderitem__qty')).order_by(
#                 '-total_sales')[:limit]
#         except Exception as e:
#             application_logger.error(f"Error getting top selling products for vendor {self.name}: {e}")
#             return []

#     def get_revenue_trends(self, months=6):
#         """
#         Retrieves revenue trends for the vendor over the specified number of months.

#         Args:
#             months (int): The number of months to retrieve revenue trends for.

#         Returns:
#             QuerySet: A queryset containing revenue trends data grouped by month.
#         """
#         try:
#             six_months_ago = timezone.now() - timedelta(days=months * 30)  # Approximation for months
#             return CartOrder.objects.filter(vendor=self, payment_status='paid', date__gte=six_months_ago) \
#                 .annotate(month=ExtractMonth('date')).values('month').annotate(total_revenue=Sum('total'))
#         except Exception as e:
#             application_logger.error(f"Error getting revenue trends for vendor {self.name}: {e}")
#             return []

#     def get_customer_behavior(self):
#         """
#         Retrieves customer behavior data for the vendor, grouped by hour.
#         """
#         try:
#             return CartOrder.objects.filter(vendor=self, payment_status='paid') \
#                 .annotate(hour=F('date__hour')).values('hour').annotate(order_count=Count('id'))
#         except Exception as e:
#             application_logger.error(f"Error getting customer behavior for vendor {self.name}: {e}")
#             return []

#     def get_low_stock_alerts(self, threshold=5):
#         """
#         Retrieves products with stock levels below the specified threshold.

#         Args:
#             threshold (int): The stock level threshold.

#         Returns:
#             QuerySet: A queryset containing products with low stock.
#         """
#         try:
#             return Product.objects.filter(vendor=self, stock_qty__lt=threshold).values('title', 'stock_qty')
#         except Exception as e:
#             application_logger.error(f"Error getting low stock alerts for vendor {self.name}: {e}")
#             return []

#     def get_review_count(self):
#         """
#         Retrieves the count of reviews associated with the vendor's products.
#         """
#         try:
#             return Review.objects.filter(product__vendor=self).count()
#         except Exception as e:
#             application_logger.error(f"Error getting review count for vendor {self.name}: {e}")
#             return 0

#     def get_average_review_rating(self):
#         """
#         Retrieves the average review rating for the vendor's products.
#         """
#         try:
#             return Review.objects.filter(product__vendor=self).aggregate(avg_rating=Avg('rating'))['avg_rating'] or 0
#         except Exception as e:
#             application_logger.error(f"Error getting average review rating for vendor {self.name}: {e}")
#             return 0

#     def get_coupon_data(self):
#         """
#         Retrieves coupon data for the vendor.
#         """
#         try:
#             return Coupon.objects.filter(vendor=self).values('code', 'discount', 'date')
#         except Exception as e:
#             application_logger.error(f"Error getting coupon data for vendor {self.name}: {e}")
#             return []

#     def get_abandoned_carts(self):
#         """
#         Retrieves abandoned carts for the vendor (carts with 'pending' payment status).
#         """
#         try:
#             return CartOrder.objects.filter(vendor=self, payment_status='pending').values('buyer__email', 'total')
#         except Exception as e:
#             application_logger.error(f"Error getting abandoned carts for vendor {self.name}: {e}")
#             return []

#     def calculate_average_order_value(self):
#         """
#         Calculates the average order value for the vendor's fulfilled orders.
#         """
#         try:
#             return CartOrder.objects.filter(vendor=self, payment_status="Fulfilled").aggregate(
#                 avg_order_value=Avg('total'))['avg_order_value'] or 0
#         except Exception as e:
#             application_logger.error(f"Error calculating average order value for vendor {self.name}: {e}")
#             return 0

#     def calculate_total_sales(self):
#         """
#         Calculates the total sales amount for the vendor's paid orders.
#         """
#         try:
#             return CartOrder.objects.filter(vendor=self, payment_status="paid").aggregate(
#                 total_sales=Sum('total'))['total_sales'] or 0
#         except Exception as e:
#             application_logger.error(f"Error calculating total sales for vendor {self.name}: {e}")
#             return 0

#     def get_total_products(self):
#         """
#         Get the total count of products associated with a given vendor.
#         """
#         try:
#             # Count all products associated with the vendor to get the total products.
#             total_products = Product.objects.filter(vendor=self).count()
#             return total_products
#         except Exception as e:
#             application_logger.error(f"Error getting total products for vendor {self.name}: {e}")
#             return 0

#     def get_active_coupons(self):
#         """
#         Get the count of active coupons for a given vendor.
#         """
#         try:
#             # Count all active coupons associated with the vendor.
#             active_coupons = Coupon.objects.filter(vendor=self, active=True).count()
#             return active_coupons
#         except Exception as e:
#             application_logger.error(f"Error getting active coupons for vendor {self.name}: {e}")
#             return 0

#     def get_inactive_coupons(self):
#         """
#         Get the count of inactive coupons for a given vendor.
#         """
#         try:
#             # Count all inactive coupons associated with the vendor.
#             inactive_coupons = Coupon.objects.filter(vendor=self, active=False).count()
#             return inactive_coupons
#         except Exception as e:
#             application_logger.error(f"Error getting inactive coupons for vendor {self.name}: {e}")
#             return 0

#     def get_total_customers(self):
#         """
#         Get the total count of unique customers who have placed orders with a given vendor.
#         """
#         try:
#             # Count the unique buyers associated with cart orders for the vendor.
#             total_customers = CartOrder.objects.filter(vendor=self).values('buyer').distinct().count()
#             return total_customers
#         except Exception as e:
#             application_logger.error(f"Error getting total customers for vendor {self.name}: {e}")
#             return 0

#     def get_todays_sales(self):
#         """
#         Calculate the total sales for a given vendor for today.
#         """
#         try:
#             # Calculate the sum of all order totals for the vendor where payment status is "paid" and the order was created today.
#             today = timezone.now().date()
#             todays_sales = CartOrder.objects.filter(vendor=self, payment_status="paid", date__date=today).aggregate(
#                 total_sales=Sum('total'))['total_sales'] or 0
#             return todays_sales
#         except Exception as e:
#             application_logger.error(f"Error getting today's sales for vendor {self.name}: {e}")
#             return 0

#     def get_this_month_sales(self):
#         """
#         Calculate the total sales for a given vendor for the current month.
#         """
#         try:
#             # Calculate the sum of all order totals for the vendor where payment status is "paid" and the order was created in the current month.
#             now = timezone.now()
#             this_month_sales = CartOrder.objects.filter(vendor=self, payment_status="paid", date__month=now.month,
#                                                          date__year=now.year).aggregate(total_sales=Sum('total'))[
#                                    'total_sales'] or 0
#             return this_month_sales
#         except Exception as e:
#             application_logger.error(f"Error getting this month's sales for vendor {self.name}: {e}")
#             return 0

#     def get_year_to_date_sales(self):
#         """
#         Calculate the total sales for a given vendor for the year to date.
#         """
#         try:
#             # Calculate the sum of all order totals for the vendor where payment status is "paid" and the order was created in the current year.
#             now = timezone.now()
#             year_to_date_sales = CartOrder.objects.filter(vendor=self, payment_status="paid", date__year=now.year).aggregate(
#                 total_sales=Sum('total'))['total_sales'] or 0
#             return year_to_date_sales
#         except Exception as e:
#             application_logger.error(f"Error getting year-to-date sales for vendor {self.name}: {e}")
#             return 0

#     def get_new_customers_this_month(self):
#         """
#         Get the count of new customers for a given vendor for the current month.
#         """
#         try:
#             # Count the unique buyers who placed their first order with the vendor in the current month.
#             now = timezone.now()
#             # Retrieve all customers for the current vendor and month
#             customers = CartOrder.objects.filter(vendor=self, date__month=now.month, date__year=now.year).values(
#                 'buyer')

#             # Determine the number of these customers who have only made one order this month
#             new_customers_this_month = 0
#             for customer in customers:
#                 customer_order_count = CartOrder.objects.filter(buyer=customer['buyer'], date__month=now.month,
#                                                                  date__year=now.year).count()
#                 if customer_order_count == 1:
#                     new_customers_this_month += 1
#             return new_customers_this_month
#         except Exception as e:
#             application_logger.error(f"Error getting new customers this month for vendor {self.name}: {e}")
#             return 0

#     def get_top_performing_categories(self):
#         """
#         Get the top-performing product categories for a given vendor based on sales revenue.
#         """
#         try:
#             # Retrieve the top-performing categories based on the sum of order totals for products in each category.

#             top_categories = Product.objects.filter(vendor=self).values('category__name').annotate(
#                 sales=Sum('cartorderitem__total')).order_by('-sales')[:5]
#             return list(top_categories)
#         except Exception as e:
#             application_logger.error(f"Error getting top-performing categories for vendor {self.name}: {e}")
#             return []

#     def get_payment_method_distribution(self):
#         """
#         Get the distribution of payment methods used by customers for a given vendor.
#         """
#         try:
#             # payment_method_distribution = CartOrder.objects.filter(vendor=vendor).values('payment_method').annotate(count=Count('id'))
#             # return list(payment_method_distribution)

#             # Aggregate the total amount associated with each method
#             payment_methods = CartOrder.objects.filter(vendor=self).values('payment_status').annotate(total=Sum('total'))
#             # Calculate the percentage distribution
#             total_revenue = sum(method['total'] for method in payment_methods)
#             payment_distribution = []

#             if total_revenue > 0:
#                 for method in payment_methods:
#                     percentage = (method['total'] / total_revenue) * 100
#                     payment_distribution.append({
#                         'payment_method': method['payment_status'],
#                         'percentage': round(percentage, 2)
#                     })
#             return payment_distribution
#         except Exception as e:
#             application_logger.error(f"Error getting payment method distribution for vendor {self.name}: {e}")
#             return []








