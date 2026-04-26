# apps/client/apis/sync/order_views.py
"""
Client Order API — DRF Sync Views
=================================

Provides read access to the client's purchase history.
Handles listing and detail retrieval of confirmed (paid) orders.

URL prefix: /api/v1/client/orders/

Design Principles:
  - Scoping: Strictly filters orders by buyer ownership and payment status.
  - Security: Uses public 'oid' strings instead of internal database PKs.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.client.legacy_compat import LegacyCommerceUnavailable, get_legacy_store_model
from apps.client.serializers.order_serializers import ClientCartOrderSerializer
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


def _commerce_unavailable_response():
    return error_response(
        message="Client order history is temporarily unavailable while the order domain migration is completing.",
        code="commerce_domain_migration_pending",
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class ClientOrderListView(generics.GenericAPIView):
    serializer_class = ClientCartOrderSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, *args, **kwargs):
        try:
            CartOrder = get_legacy_store_model("CartOrder")
        except LegacyCommerceUnavailable:
            logger.warning("ClientOrderListView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response()

        orders = (
            CartOrder.objects.filter(buyer=request.user, payment_status="paid")
            .prefetch_related("orderitem", "orderitem__product")
            .order_by("-date")
        )
        serializer = self.get_serializer(orders, many=True)
        return success_response(
            data=serializer.data,
            message="Orders retrieved successfully.",
        )


class ClientOrderDetailView(generics.GenericAPIView):
    serializer_class = ClientCartOrderSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, oid: str, *args, **kwargs):
        try:
            CartOrder = get_legacy_store_model("CartOrder")
        except LegacyCommerceUnavailable:
            logger.warning("ClientOrderDetailView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response()

        try:
            order = (
                CartOrder.objects.filter(buyer=request.user, payment_status="paid")
                .prefetch_related("orderitem", "orderitem__product")
                .get(oid=oid)
            )
        except ObjectDoesNotExist:
            return error_response(
                message="Order not found.",
                code="order_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(order)
        return success_response(
            data=serializer.data,
            message="Order retrieved successfully.",
        )
