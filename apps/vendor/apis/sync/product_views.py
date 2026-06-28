# apps/vendor/apis/sync/product_views.py
"""
Vendor Product Management — DRF Sync Views.

URL prefix: /api/v1/vendor/

Endpoints:
  POST   /api/v1/vendor/products/create/                 — create product
  GET    /api/v1/vendor/products/filter/                 — filter by status
  PUT    /api/v1/vendor/products/<str:product_pid>/edit/  — full update
  PATCH  /api/v1/vendor/products/<str:product_pid>/edit/  — partial update
  DELETE /api/v1/vendor/products/<str:product_pid>/delete/ — delete
  PATCH  /api/v1/vendor/orders/<int:order_id>/status/    — order status update

All DB access scoped via vendor_products reverse FK (no N+1).
"""

import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from apps.vendor.serializers.product_serializers import (
    VendorOrderStatusSerializer,
)

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_profile_or_404(user):
    """Return vendor profile or raise ValueError."""
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


# ══════════════════════════════════════════════════════════════════
#  Order Status Update (vendor-side)
# ══════════════════════════════════════════════════════════════════

ALLOWED_ORDER_STATUSES = {"Pending", "Processing", "Shipped", "Fulfilled", "Cancelled"}


class VendorOrderStatusUpdateView(generics.UpdateAPIView):
    """
    PATCH /api/v1/vendor/orders/<int:order_id>/status/

    Update order_status for a vendor's own order.
    Allowed values: Pending, Processing, Shipped, Fulfilled, Cancelled.
    Payment status (paid/unpaid) is immutable here — managed by payment gateway.
    """

    serializer_class = VendorOrderStatusSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_url_kwarg = "order_id"
    lookup_field = "pk"

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_orders.all()
        except ValueError:
            from apps.order.models import Order
            return Order.objects.none()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        new_status = request.data.get("order_status", "").strip()
        if new_status not in ALLOWED_ORDER_STATUSES:
            return error_response(
                message=f"Invalid order_status. Allowed: {sorted(ALLOWED_ORDER_STATUSES)}",
                status=status.HTTP_400_BAD_REQUEST,
            )

        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        old_status = instance.order_status

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        logger.info(
            "Order %s status changed: %s → %s by vendor=%s",
            instance.pk,
            old_status,
            new_status,
            request.user.pk,
        )
        return success_response(
            data=serializer.data,
            message=f"Order status updated to '{new_status}'.",
        )
