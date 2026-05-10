# apps/client/apis/sync/order_views.py
"""
Client Order API — DRF Sync Views
=================================
All endpoints scoped to authenticated client via IsClient permission.
Uses the enterprise apps.order domain (NOT legacy store.CartOrder).

URL prefix: /api/v1/client/

Endpoints:
  GET  /api/v1/client/orders/             — list all paid orders
  GET  /api/v1/client/orders/<str:oid>/  — single order detail
"""

import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.client.serializers.order_serializers import ClientCartOrderSerializer
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer

logger = logging.getLogger(__name__)


# ===========================================================================
# ORDER HISTORY
# ===========================================================================


class ClientOrderListView(generics.ListAPIView):
    """
    GET /api/v1/client/orders/

    Return all paid orders for the authenticated client.
    Prefetches orderitems to avoid N+1 on order detail pages.
    Returns a list of all successful orders placed by the client.

    Validation Logic:
      - Filter: Only returns orders where payment_status is 'paid'.
      - Ordering: Date-descending (most recent first).

    Security:
      - Requires IsAuthenticated + IsClient.

    Status Codes:
      200 OK: List of orders returned.
    """

    serializer_class = ClientCartOrderSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        user = self.request.user

        return (
            user.client_profile.user_orders.filter(payment_status="paid")
            .prefetch_related("items", "items__product")
            .select_related("buyer")
            .order_by("-created_at")
        )


class ClientOrderDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/client/orders/<str:oid>/

    Return detail for a single paid order scoped to this client.
    Uses oid (order identifier) — not PK — for public safety.

    Status Codes:
      200 OK: Order details returned.
      404 Not Found: Order missing or unauthorized.
    """

    serializer_class = ClientCartOrderSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_field = "oid"
    lookup_url_kwarg = "oid"

    def get_queryset(self):
        user = self.request.user
        return (
            user.client_profile.user_orders.filter(payment_status="paid")
            .prefetch_related("items", "items__product")
            .select_related("buyer")
        )
