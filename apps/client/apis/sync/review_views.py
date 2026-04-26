# apps/client/apis/sync/review_views.py
"""
Client Review API — DRF Sync Views
==================================

Handles product feedback, ratings, and customer testimonials.
Separates public viewing (AllowAny) from authenticated contribution (IsClient).

URL prefix: /api/v1/client/ and /api/v1/home/

Design Principles:
  - Transparency: Publicly exposes approved reviews for marketplace trust.
  - Accountability: Restricts creation to authenticated clients.
"""

import logging
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.responses import success_response, error_response
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.client.serializers.review_serializers import ClientReviewSerializer
from store.models import Review

logger = logging.getLogger(__name__)


# ===========================================================================
# PUBLIC FEEDBACK
# ===========================================================================


class ProductReviewListView(generics.ListAPIView):
    """
    Lists all approved reviews for a specific product.

    Validation Logic:
      - Filter: Only returns reviews where active=True.
      - Optimization: select_related('user__profile') to avoid N+1 queries.

    Security:
      - Requires AllowAny (Public visibility).

    Status Codes:
      200 OK: List of reviews returned.
    """
    serializer_class = ClientReviewSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        product_id = self.kwargs.get("product_id")
        return (
            Review.objects
            .filter(product_id=product_id, active=True)
            .select_related("product", "user", "user__profile")
            .order_by("-date")
        )


# ===========================================================================
# CUSTOMER CONTRIBUTION
# ===========================================================================


class ClientReviewCreateView(generics.CreateAPIView):
    """
    Submits a new rating and review for a product.

    Validation Logic:
      - Payload: Validates product_id presence and rating (1–5 scale).
      - Duplication: Enforces unique review per user/product.

    Security:
      - Requires IsAuthenticated + IsClient.

    Status Codes:
      201 Created: Review successfully recorded.
      400 Bad Request: Missing product_id or invalid rating.
    """
    serializer_class = ClientReviewSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def create(self, request, *args, **kwargs):
        product_id = request.data.get("product_id")
        if not product_id:
            return error_response(
                message="product_id is required.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data.copy()
        data['product'] = product_id
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        logger.info(
            "Review created: product=%s rating=%s user=%s",
            product_id, data.get('rating'), request.user.email,
        )
        return success_response(
            data=serializer.data,
            message="Review submitted successfully.",
            status=status.HTTP_201_CREATED,
            headers=headers
        )

