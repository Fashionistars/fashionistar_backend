# apps/client/apis/sync/order_views.py
"""
Client Order API — DRF Sync Views.

Migrated & modernized from legacy customer/orders.py.
All endpoints scoped to authenticated client via IsClient permission.

URL prefix: /api/v1/client/

Endpoints:
  GET  /api/v1/client/orders/              — list all paid orders
  GET  /api/v1/client/orders/<str:oid>/   — single order detail
"""
import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsClient

logger = logging.getLogger(__name__)


class ClientOrderListView(generics.GenericAPIView):
    """
    GET /api/v1/client/orders/

    Return all paid orders for the authenticated client.
    Prefetches orderitems to avoid N+1 on order detail pages.
    """

    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request):
        from store.models import CartOrder  # lazy — store app FK reference
        from store.serializers import CartOrderSerializer

        orders = (
            CartOrder.objects.filter(buyer=request.user, payment_status="paid")
            .prefetch_related("orderitem")
            .order_by("-date")
        )
        serializer = CartOrderSerializer(orders, many=True)
        logger.info(
            "ClientOrderListView: %d orders for user=%s",
            orders.count(),
            request.user.email,
        )
        return Response(
            {
                "status": "success",
                "count": orders.count(),
                "data": serializer.data,
            }
        )


class ClientOrderDetailView(generics.GenericAPIView):
    """
    GET /api/v1/client/orders/<str:oid>/

    Return detail for a single paid order scoped to this client.
    Uses oid (order identifier) — not PK — for public safety.
    """

    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request, oid: str):
        from store.models import CartOrder
        from store.serializers import CartOrderSerializer

        try:
            order = CartOrder.objects.prefetch_related("orderitem").get(
                buyer=request.user, payment_status="paid", oid=oid
            )
        except CartOrder.DoesNotExist:
            logger.warning(
                "ClientOrderDetailView: oid=%s not found for user=%s",
                oid,
                request.user.email,
            )
            return Response(
                {"status": "error", "message": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CartOrderSerializer(order)
        return Response({"status": "success", "data": serializer.data})
