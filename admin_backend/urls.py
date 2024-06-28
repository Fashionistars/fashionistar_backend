# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from admin_backend import views as admin_backend


# Oders Profit
from admin_backend import orders as arder_profits

# Delivery Status
from admin_backend import delivery as deliverystatus



app_name = 'admin_backend'  # Add this line to specify the app namespace


router = DefaultRouter()
router.register(r'collections', admin_backend.CollectionsViewSet, basename='collections')
router.register(r'categories', admin_backend.CategoryViewSet, basename='categories')
router.register(r'brand', admin_backend.BrandViewSet, basename='brand')


urlpatterns = [
    path('', include(router.urls)),

    
    path('admin/orders/', arder_profits.AdminOrderListView.as_view(), name='admin-orders'),
    path('admin/profit/', arder_profits.AdminProfitView.as_view(), name='admin-profit'),

    
    # delivery and order tracking to be paid attention to later
    
    path('admin/order/delivery-status-update/<int:order_id>/', deliverystatus.DeliveryStatusUpdateView.as_view(), name='delivery-status-update'),
]

