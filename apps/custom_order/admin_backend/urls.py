# apps/custom_order/admin_backend/urls.py
from django.urls import path
from .views import AdminCustomOrderStatusUpdateView

urlpatterns = [
    path("<str:custom_order_id>/status/", AdminCustomOrderStatusUpdateView.as_view(), name="admin-custom-order-status-update"),
]
