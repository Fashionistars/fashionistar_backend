from django.urls import path

from .delivery import DeliveryStatusUpdateView

app_name = "admin_backend"

urlpatterns = [
    path("delivery/<order_id>/update/", DeliveryStatusUpdateView.as_view(), name="delivery-status-update"),
]
