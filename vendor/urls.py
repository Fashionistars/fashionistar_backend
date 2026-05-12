from django.urls import path

from vendor import views as vendor_views
from django.urls import path
from userauths import views as userauths_views
from store import views as store_views
from vendor.withdrawal import wallet_balance as wallet_balance


from Paystack_Webhoook_Prod import BankAccountDetails as bank_details_views
from Paystack_Webhoook_Prod import VendorWithdrawView as vendor_withrawal_views



app_name = 'vendor'  # Add this line to specify the app namespace


urlpatterns = [
    path('vendor/bank-details/create/', bank_details_views.VendorBankDetailsCreateView.as_view()),
    path('vendor/bank-details/list/', bank_details_views.VendorBankDetailsListView.as_view()),
    path('vendor/bank-details/update/<str:pk>/', bank_details_views.VendorBankDetailsUpdateView.as_view()),
    path('vendor/bank-details/delete/<str:pk>/', bank_details_views.VendorBankDetailsDeleteView.as_view()),
    path('vendor/bank-details/<str:pk>/', bank_details_views.VendorBankDetailsDetailView.as_view()),



    # --------------------        WITHDRAWAL               -----------------------------
    path('vendor/withdraw/transfer/', vendor_withrawal_views.VendorWithdrawView.as_view(), name='vendor-withdraw-transfer'),


    
    path('vendor/wallet-balance/', wallet_balance.VendorWalletBalanceView.as_view()),
    
    
    


    path('vendor/<int:vendor_id>/store/', vendor_views.VendorStoreView.as_view(), name='vendor-store-products'),
    path('vendors/', vendor_views.AllVendorsProductsList.as_view(), name='all-vendors-products'),
    path('vendors/all', vendor_views.VENDORListView.as_view(), name='all-AllVENDORSerializer-products'),

    # Vendor API Endpoints
    # path('vendor/dashboard', vendor_views.DashboardStatsAPIView.as_view(), name='vendor-stats'),
    path('vendor/orders/', vendor_views.OrdersAPIView.as_view(), name='vendor-orders'),
    path('vendor/orders/<str:order_oid>/', vendor_views.OrderDetailAPIView.as_view(), name='vendor-order-detail'),
    
    path('vendor/monthly-earning/<vendor_id>/', vendor_views.MonthlyEarningTracker, name='vendor-product-filter'),
    path('vendor/orders-report-chart/<vendor_id>/', vendor_views.MonthlyOrderChartAPIFBV, name='vendor-orders-report-chart'),
    path('vendor/yearly-report/<vendor_id>/', vendor_views.YearlyOrderReportChartAPIView.as_view(), name='vendor-yearly-report'),
    path('vendor/product/<vendor_id>/', vendor_views.ProductsAPIView.as_view(), name='vendor-prdoucts'),
    path('vendor/products-report-chart/<vendor_id>/', vendor_views.MonthlyProductsChartAPIFBV, name='vendor-product-report-chart'),
    path('vendor/product-create', vendor_views.ProductCreateView.as_view(), name='vendor-product-create'),
    path('vendor/product-edit/<vendor_id>/<product_pid>/', vendor_views.ProductUpdateAPIView.as_view(), name='vendor-product-edit'),
    path('vendor/product-delete/<vendor_id>/<product_pid>/', vendor_views.ProductDeleteAPIView.as_view(), name='vendor-product-delete'),
    path('vendor/product-filter/<vendor_id>', vendor_views.FilterProductsAPIView.as_view(), name='vendor-product-filter'),
    path('vendor/earning/<vendor_id>/', vendor_views.Earning.as_view(), name='vendor-product-filter'),
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