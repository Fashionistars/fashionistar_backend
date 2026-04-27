# apps/order/urls.py
from django.urls import path
from apps.order.apis.sync.order_views import (
    ClientOrderListView,
    PlaceOrderView,
    ClientOrderDetailView,
    ClientCancelOrderView,
    ConfirmDeliveryView,
    VendorOrderListView,
    VendorOrderDetailView,
    VendorOrderTransitionView,
)

app_name = "order"

urlpatterns = [
    # ── Client ─────────────────────────────────────────────────────────────────
    path("", ClientOrderListView.as_view(), name="client-order-list"),
    path("place/", PlaceOrderView.as_view(), name="place-order"),
    path("<uuid:order_id>/", ClientOrderDetailView.as_view(), name="client-order-detail"),
    path("<uuid:order_id>/cancel/", ClientCancelOrderView.as_view(), name="client-order-cancel"),
    path("<uuid:order_id>/confirm-delivery/", ConfirmDeliveryView.as_view(), name="confirm-delivery"),
    # ── Vendor ─────────────────────────────────────────────────────────────────
    path("vendor/", VendorOrderListView.as_view(), name="vendor-order-list"),
    path("vendor/<uuid:order_id>/", VendorOrderDetailView.as_view(), name="vendor-order-detail"),
    path("vendor/<uuid:order_id>/transition/", VendorOrderTransitionView.as_view(), name="vendor-order-transition"),
]
