# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CollectionsViewSet
from admin_backend import views as admin_backend

router = DefaultRouter()
router.register(r'collections', admin_backend.CollectionsViewSet, basename='collections')
router.register(r'categories', admin_backend.CategoryViewSet, basename='categories')
router.register(r'brand', admin_backend.BrandViewSet, basename='brand')


urlpatterns = [
    path('', include(router.urls)),
]