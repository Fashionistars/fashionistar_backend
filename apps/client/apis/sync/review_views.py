# apps/client/apis/sync/review_views.py
"""
Client Review API — DRF Sync Views
==================================

Handles product feedback, ratings, and customer testimonials.
Separates public viewing (AllowAny) from authenticated contribution (IsClient).

URL prefix: /api/v1/client/
Endpoints:
  POST /api/v1/client/reviews/create/  — create review (client only)
"""

import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.client.serializers.review_serializers import ClientReviewSerializer
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


# ===========================================================================
# CUSTOMER CONTRIBUTION
# ===========================================================================


class ClientReviewCreateView(generics.CreateAPIView):
    """
    POST /api/v1/client/reviews/create/

    Submits a new rating and review for a product.

    Validation Logic:
      - Payload: Validates product_id presence and rating (1–5 scale).
      - Duplication: Enforced at serializer / model level.

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
        data["product_id"] = product_id

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        logger.info(
            "Review created: product=%s rating=%s user=%s",
            product_id,
            data.get("rating"),
            getattr(request.user, "email", str(request.user.pk)),
        )
        return success_response(
            data=serializer.data,
            message="Review submitted successfully.",
            status=status.HTTP_201_CREATED,
        )
