# apps/product/admin_backend/urls.py
from django.urls import path
from apps.product.admin_backend.views import (
    AdminProductApproveView,
    AdminProductRejectView,
    AdminInventoryAdjustView,
    AdminProductDeleteView,
)

app_name = "admin_product"

urlpatterns = [
    path("<product_id>/approve/", AdminProductApproveView.as_view(), name="approve"),
    path("<product_id>/reject/", AdminProductRejectView.as_view(), name="reject"),
    path("<product_id>/adjust-inventory/", AdminInventoryAdjustView.as_view(), name="adjust-inventory"),
    path("<product_id>/delete/", AdminProductDeleteView.as_view(), name="delete"),
]

