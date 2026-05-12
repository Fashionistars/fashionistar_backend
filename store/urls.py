from django.urls import path

from store import views as store_views




app_name = 'store'  # Add this line to specify the app namespace

urlpatterns = [

    #     NEW TESTABLE ENDPOINTS



   
    # Store API Endpoints
    # path('products/', store_views.ProductListView.as_view(), name='products'),
    # path('products/<slug:slug>/', store_views.ProductDetailView.as_view(), name='product-details'),
    path('featured-products/', store_views.FeaturedProductListView.as_view(), name='featured-products'),
    path('coupon/', store_views.CouponApiView.as_view(), name='coupon'),
    path('create-review/', store_views.ReviewRatingAPIView.as_view(), name='create-review'),
    path('reviews/<product_id>/', store_views.ReviewListView.as_view(), name='create-review'),
    path('search/', store_views.SearchProductsAPIView.as_view(), name='search'),



]




