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
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.client.serializers.order_serializers import ClientCartOrderSerializer
from store.models import CartOrder

logger = logging.getLogger(__name__)


# ===========================================================================
# ORDER HISTORY
# ===========================================================================


class ClientOrderListView(generics.ListAPIView):
    """
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
        return (
            CartOrder.objects.filter(buyer=self.request.user, payment_status="paid")
            .prefetch_related("orderitem", "orderitem__product")
            .order_by("-date")
        )


class ClientOrderDetailView(generics.RetrieveAPIView):
    """
    Retrieves detailed information for a single confirmed order.

    Validation Logic:
      - Scoped: Ensures the order belongs to the requesting client.

    Security:
      - Lookup: Uses the unique 'oid' identifier for lookup.

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
        return (
            CartOrder.objects.filter(buyer=self.request.user, payment_status="paid")
            .prefetch_related("orderitem", "orderitem__product")
        )

