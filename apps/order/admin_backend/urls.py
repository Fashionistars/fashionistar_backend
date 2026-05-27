# apps/order/admin_backend/urls.py
from django.urls import path
from apps.order.admin_backend.views import (
    AdminOrderStatusTransitionView,
    AdminOrderReleaseEscrowView,
    AdminOrderCancelView,
)

app_name = "admin_order"

urlpatterns = [
    path("<str:pk>/transition/", AdminOrderStatusTransitionView.as_view(), name="order-transition"),
    path("<str:pk>/release-escrow/", AdminOrderReleaseEscrowView.as_view(), name="order-release-escrow"),
    path("<str:pk>/cancel/", AdminOrderCancelView.as_view(), name="order-cancel"),
]
