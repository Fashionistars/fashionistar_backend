from django.urls import path, include

from Homepage.collections import *
from Homepage.category import *
from Homepage.brand import *

# Oders Profit
from admin_backend import order_view as order_profits

# Delivery Status
from admin_backend import delivery as deliverystatus

from rest_framework.routers import DefaultRouter

# chat list and details
from admin_backend.chat_view import AdminMessageListView, AdminMessageDetailView
from .views import CategoryViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')



app_name = 'admin_backend'  # Add this line to specify the app namespace


# # Protected routes endpoints
admin_urlpatterns = [
    # Category endpoints
    path('admin/category/create/', CategoryViewSet.as_view({'post': 'create'}), name='category-create'),
    path('admin/category/all/', CategoryViewSet.as_view({'get': 'list'}), name='category-list'),
    path('admin/category/<slug:slug>/', CategoryViewSet.as_view({'get': 'retrieve'}), name='category-detail'),
    path('admin/category/<slug:slug>/update/', CategoryViewSet.as_view({'put': 'update'}), name='category-update'),
    path('admin/category/<slug:slug>/delete/', CategoryViewSet.as_view({'delete': 'destroy'}), name='category-delete'),    # path('admin/categories/create/', CategoryCreateView.as_view(), name='category-create'),
    # path('admin/categories/<slug:slug>/update/', CategoryUpdateView.as_view(), name='category-update'),
    # path('admin/categories/<slug:slug>/delete/', CategoryDeleteView.as_view(), name='category-delete'),


    # Brand endpoints
    path('admin/brands/create/', BrandCreateView.as_view(), name='brand-create'),
    path('admin/brands/<slug:slug>/update/', BrandUpdateView.as_view(), name='brand-update'),
    path('admin/brands/<slug:slug>/delete/', BrandDeleteView.as_view(), name='brand-delete'),

    # Collections endpoints
    path('admin/collections/create/', CollectionsCreateView.as_view(), name='collection-create'),
    path('admin/collections/<slug:slug>/update/', CollectionsUpdateView.as_view(), name='collection-update'),
    path('admin/collections/<slug:slug>/delete/', CollectionsDeleteView.as_view(), name='collection-delete'),
]
    
   

   
urlpatterns = [
    
    path('admin/orders/', order_profits.AdminOrderListView.as_view(), name='admin-orders'),
    path('admin/profit/', order_profits.AdminProfitView.as_view(), name='admin-profit'),

    
    # delivery and order tracking to be paid attention to later
    
    path('admin/order/delivery-status-update/<int:order_id>/', deliverystatus.DeliveryStatusUpdateView.as_view(), name='delivery-status-update'),

    # chat mesages list and details
    path('admin/list-messages/', AdminMessageListView.as_view(), name='admin-message-list'),
    path('admin/message-details/<int:pk>/', AdminMessageDetailView.as_view(), name='admin-message-detail'),

]


# Combine both sets of urlpatterns
urlpatterns += admin_urlpatterns



