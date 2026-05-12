from django.urls import path

from store import views as store_views


from Homepage.product import *
from Homepage.collections import *
from Homepage.category import *
from Homepage.brand import *

app_name = 'home'  # Add this line to specify the app namespace


urlpatterns = [
    ###########   # Unprotected endpoints     ##########
    

    # PRODUCTS ENDPOINTS 
    path('home/products/', ProductListView.as_view(), name='product-list'),
    path('home/product/<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),   
    


    # Category endpoints
    path('home/categories/', CategoryListView.as_view(), name='categories-list'),
    path('home/categories/<slug:slug>/', CategoryDetailView.as_view(), name='category-detail'),
   
   
    # Brand endpoints
    path('home/brands/', BrandListView.as_view(), name='brand-list'),
    path('home/brands/<slug:slug>/', BrandDetailView.as_view(), name='brand-detail'),


    # Collections endpoints
    path('home/collections/', CollectionsListView.as_view(), name='collections-list'),
    path('home/collections/<slug:slug>/', CollectionsDetailView.as_view(), name='collection-detail'),




    
    # Store API Endpoints
    path('coupon/', store_views.CouponApiView.as_view(), name='coupon'),
    path('create-review/', store_views.ReviewRatingAPIView.as_view(), name='create-review'),
    path('reviews/<product_id>/', store_views.ReviewListView.as_view(), name='create-review'),
    path('search/', store_views.SearchProductsAPIView.as_view(), name='search'),

]

