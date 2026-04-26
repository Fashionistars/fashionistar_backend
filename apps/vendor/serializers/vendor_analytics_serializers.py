# apps/vendor/serializers/vendor_analytics_serializers.py
from rest_framework import serializers

class VendorAnalyticsSummarySerializer(serializers.Serializer):
    todays_sales = serializers.CharField()
    this_month_sales = serializers.CharField()
    year_to_date_sales = serializers.CharField()
    average_order_value = serializers.CharField()
    total_customers = serializers.IntegerField()
    review_count = serializers.IntegerField()
    average_rating = serializers.CharField()
    active_coupons = serializers.IntegerField()
    inactive_coupons = serializers.IntegerField()
    low_stock_count = serializers.IntegerField()
    total_products = serializers.IntegerField()
    total_sales = serializers.IntegerField()
    total_revenue = serializers.CharField()
    wallet_balance = serializers.CharField()

class VendorRevenueTrendSerializer(serializers.Serializer):
    month = serializers.IntegerField(required=False)
    year = serializers.IntegerField(required=False)
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)

class VendorMonthlyOrderSerializer(serializers.Serializer):
    month = serializers.IntegerField()
    order_status = serializers.CharField()
    count = serializers.IntegerField()

class VendorMonthlyProductSerializer(serializers.Serializer):
    month = serializers.IntegerField()
    count = serializers.IntegerField()

class VendorEarningTrackerSerializer(serializers.Serializer):
    todays_sales = serializers.CharField()
    this_month_sales = serializers.CharField()
    last_month_sales = serializers.CharField()
    year_to_date = serializers.CharField()
    total_earnings = serializers.CharField()
    wallet_balance = serializers.CharField()
    pending_payouts = serializers.CharField()

class VendorCustomerBehaviorSerializer(serializers.Serializer):
    hourly_distribution = serializers.ListField(child=serializers.DictField())
    new_customers_this_month = serializers.IntegerField()
    total_customers = serializers.IntegerField()

class VendorCategoryPerformanceSerializer(serializers.Serializer):
    category__name = serializers.CharField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    order_count = serializers.IntegerField()

class VendorPaymentDistributionSerializer(serializers.Serializer):
    payment_status = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()

class VendorProductListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    stock_qty = serializers.IntegerField()
    status = serializers.CharField()
    category__name = serializers.CharField()
    date = serializers.DateTimeField()

class VendorOrderListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_status = serializers.CharField()
    order_status = serializers.CharField()
    date = serializers.DateTimeField()
    buyer__email = serializers.EmailField()

class VendorOrderDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    total = serializers.CharField()
    payment_status = serializers.CharField()
    order_status = serializers.CharField()
    date = serializers.DateTimeField()
    buyer_email = serializers.EmailField()

class VendorReviewListSerializer(serializers.Serializer):
    review_product__id = serializers.IntegerField()
    review_product__rating = serializers.IntegerField()
    review_product__review = serializers.CharField()
    review_product__date = serializers.DateTimeField()
    title = serializers.CharField()

class VendorCouponListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    discount = serializers.IntegerField()
    date = serializers.DateTimeField()
    active = serializers.BooleanField()
