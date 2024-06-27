# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from admin_backend import views as admin_backend


# Oders Profit
from admin_backend import orders as arder_profits



router = DefaultRouter()
router.register(r'collections', admin_backend.CollectionsViewSet, basename='collections')
router.register(r'categories', admin_backend.CategoryViewSet, basename='categories')
router.register(r'brand', admin_backend.BrandViewSet, basename='brand')


urlpatterns = [
    path('', include(router.urls)),

    
    path('admin/orders/', arder_profits.AdminOrderListView.as_view(), name='admin-orders'),
    path('admin/profit/', arder_profits.AdminProfitView.as_view(), name='admin-profit'),
]

