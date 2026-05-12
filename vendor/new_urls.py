# vendor/new_urls.py

from django.urls import path


#########  NEW PRDUCT # TESTING ENDPOINT S ###########
from vendor.Views import product1 as product_views # TESTING
from vendor.Views import product2 as product_views2 # TESTING

from vendor.Views import product_list as product_list # TESTING
from vendor.Views import product_update as product_update # TESTING
from vendor.Views import product_delete as product_delete # TESTING


from vendor.Views import dashboard # TESTING
from vendor.Views import chart_dashboard # TESTING


from vendor.Views import order # TESTING



# +++++++++++++++    TESTING NEW PRODUCTS FORM PARSER CLASSES  WITH NEW ENDPOINTS
urlpatterns = [


    # VENDOR DASHBOARD URLS
    path('new-vendor/dashboard/stats/', dashboard.DashboardStatsAPIView.as_view(), name='vendor-dashboard-stats'), 
    path('new-vendor/dashboard/charts/total-orders/', chart_dashboard.TotalOrdersChartAPIView.as_view(), name='vendor-chart-total-orders'), # <-- ADD THIS LINE
    path('new-vendor/dashboard/charts/revenue-analytics/', chart_dashboard.RevenueAnalyticsChartAPIView.as_view(), name='vendor-chart-revenue-analytics'), 


    # # VENDOR PRODUCT MANAGEMENT URLS
    # path('vendor/productcreate', product_views.ProductCreateView.as_view(), name='vendor-product-create'),
    # path('vendor/productcreate2', product_views2.ProductCreateAPIView.as_view(), name='vendor-productcreate2'),

    path('new-vendor/catalog/', product_list.VendorProductListView.as_view(), name='vendor-product-list'), # <-- ADD THIS LINE
    path('new-vendor/product/update/<str:product_pid>/', product_update.ProductUpdateAPIView.as_view(), name='vendor-product-update'),
    path('new-vendor/product/delete/<str:product_pid>/', product_delete.ProductDeleteAPIView.as_view(), name='vendor-product-delete'),


    # VENDOR ORDER MANAGEMENT URLS
    path('new-vendor/orders/', order.VendorOrderListView.as_view(), name='vendor-order-list'),
    path('new-vendor/orders/<str:order_oid>/', order.VendorOrderDetailView.as_view(), name='vendor-order-detail'),


]