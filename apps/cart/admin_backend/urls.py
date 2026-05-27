# apps/cart/admin_backend/urls.py
from django.urls import path
from .views import AdminClearCartView

urlpatterns = [
    path("<str:cart_id>/clear/", AdminClearCartView.as_view(), name="admin-cart-clear"),
]
