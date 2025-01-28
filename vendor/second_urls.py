from django.urls import path

from vendor import views as vendor_order
from vendor import views as vendor_views
from django.urls import path
from userauths import views as userauths_views
from store import views as store_views
from vendor import views as vendor_views

app_name = 'vendor'  # Add this line to specify the app namespace

urlpatterns = [
    path('vendor/withdraw/', vendor_views.VendorWithdrawView.as_view(), name='vendor-withdraw'),
      path('paystack/transfer-webhook/', vendor_views.paystack_transfer_webhook_view, name='paystack-transfer-webhook'),
    path('vendor/wallet-balance/', vendor_views.VendorWalletBalanceView.as_view()),
    path('vendor/<int:vendor_id>/store/', vendor_views.VendorStoreView.as_view(), name='vendor-store-products'),
    path('vendors/', vendor_views.AllVendorsProductsList.as_view(), name='all-vendors-products'),

    # Vendor API Endpoints
    path('vendor/dashboard', vendor_views.DashboardStatsAPIView.as_view(), name='vendor-stats'),
    path('vendor/orders/', vendor_views.OrdersAPIView.as_view(), name='vendor-orders'),
    path('vendor/orders/<str:order_oid>/', vendor_views.OrderDetailAPIView.as_view(), name='vendor-order-detail'),
    
    path('vendor/products/<vendor_id>/', vendor_views.ProductsAPIView.as_view(), name='vendor-prdoucts'),
    path('vendor/yearly-report/<vendor_id>/', vendor_views.YearlyOrderReportChartAPIView.as_view(), name='vendor-yearly-report'),
    path('vendor/orders-report-chart/<vendor_id>/', vendor_views.MonthlyOrderChartAPIFBV, name='vendor-orders-report-chart'),
    path('vendor/products-report-chart/<vendor_id>/', vendor_views.MonthlyProductsChartAPIFBV, name='vendor-product-report-chart'),
    path('vendor/product-create', vendor_views.ProductCreateView.as_view(), name='vendor-product-create'),
    path('vendor/product-edit/<vendor_id>/<product_pid>/', vendor_views.ProductUpdateAPIView.as_view(), name='vendor-product-edit'),
    path('vendor/product-delete/<vendor_id>/<product_pid>/', vendor_views.ProductDeleteAPIView.as_view(), name='vendor-product-delete'),
    path('vendor/product-filter/<vendor_id>', vendor_views.FilterProductsAPIView.as_view(), name='vendor-product-filter'),
    path('vendor/earning/<vendor_id>/', vendor_views.Earning.as_view(), name='vendor-product-filter'),
    path('vendor/monthly-earning/<vendor_id>/', vendor_views.MonthlyEarningTracker, name='vendor-product-filter'),
    path('vendor/reviews/<vendor_id>/', vendor_views.ReviewsListAPIView.as_view(), name='vendor-reviews'),
    path('vendor/reviews/<vendor_id>/<review_id>/', vendor_views.ReviewsDetailAPIView.as_view(), name='vendor-review-detail'),
    path('vendor/coupon-list/<vendor_id>/', vendor_views.CouponListAPIView.as_view(), name='vendor-coupon-list'),
    path('vendor/coupon-stats/<vendor_id>/', vendor_views.CouponStats.as_view(), name='vendor-coupon-stats'),
    path('vendor/coupon-detail/<vendor_id>/<coupon_id>/', vendor_views.CouponDetailAPIView.as_view(), name='vendor-coupon-detail'),
    path('vendor/coupon-create/<vendor_id>/', vendor_views.CouponCreateAPIView.as_view(), name='vendor-coupon-create'),
    
    path('vendor/settings/<int:pk>/', vendor_views.VendorProfileUpdateView.as_view(), name='vendor-settings'),
    path('vendor/shop-settings/<int:pk>/', vendor_views.ShopUpdateView.as_view(), name='customer-settings'),
    path('shop/<vendor_slug>/', vendor_views.ShopAPIView.as_view(), name='shop'),
    path('vendor/products/<vendor_slug>/', vendor_views.ShopProductsAPIView.as_view(), name='vendor-products'),
    path('vendor/register/', vendor_views.VendorRegister.as_view(), name='vendor-register'),
]