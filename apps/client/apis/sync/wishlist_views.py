# apps/client/apis/sync/wishlist_views.py
"""
Client Wishlist API — DRF Sync Views
====================================

Manages the client's curated collection of desired products.
Implements a smart 'toggle' pattern for adding/removing items.

URL prefix: /api/v1/client/

Endpoints:
  GET  /api/v1/client/wishlist/        — list wishlist items
  POST /api/v1/client/wishlist/toggle/ — add or remove product from wishlist
"""
import logging

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsClient

logger = logging.getLogger(__name__)


class ClientWishlistView(APIView):
    """
    GET /api/v1/client/wishlist/

    Return all wishlist items for the authenticated client.
    Products are serialized with their full nested data.
    """

    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request):
        from store.models import Wishlist
        from store.serializers import WishlistSerializer

        wishlist = (
            Wishlist.objects.filter(user=request.user)
            .select_related("product")
            .order_by("-id")
        )
        serializer = WishlistSerializer(wishlist, many=True)
        return Response(
            {
                "status": "success",
                "count": wishlist.count(),
                "data": serializer.data,
            }
        )


class ClientWishlistToggleView(APIView):
    """
    POST /api/v1/client/wishlist/toggle/

    Body: { "product_id": "<uuid>" }

    Toggle logic (from legacy customer/wishlist.py):
      - If product already in wishlist → remove it → 200
      - If product NOT in wishlist → add it → 201

    This is the recommended UX for wishlist heart buttons.
    """

    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        product_id = request.data.get("product_id")
        if not product_id:
            return Response(
                {"status": "error", "message": "product_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from store.models import Product, Wishlist

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            logger.warning(
                "ClientWishlistToggleView: product_id=%s not found", product_id
            )
            return Response(
                {"status": "error", "message": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Toggle: remove if exists, add if not
        existing = Wishlist.objects.filter(product=product, user=request.user)
        if existing.exists():
            existing.delete()
            logger.info(
                "Wishlist: removed product=%s for user=%s",
                product_id,
                request.user.email,
            )
            return Response(
                {
                    "status": "success",
                    "message": "Removed from wishlist.",
                    "action": "removed",
                },
                status=status.HTTP_200_OK,
            )

        Wishlist.objects.create(product=product, user=request.user)
        logger.info(
            "Wishlist: added product=%s for user=%s", product_id, request.user.email
        )
        return Response(
            {"status": "success", "message": "Added to wishlist.", "action": "added"},
            status=status.HTTP_201_CREATED,
        )


# apps/client/apis/sync/wishlist_views.py
"""
Client Wishlist API — DRF Sync Views
====================================

Manages the client's curated collection of desired products.
Implements a smart 'toggle' pattern for adding/removing items.

URL prefix: /api/v1/client/wishlist/

Design Principles:
  - Idempotency: Toggle endpoint ensures exactly-once state transitions.
  - Performance: Optimized with select_related for listing deep product trees.
"""

import logging
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.client.serializers.wishlist_serializers import (
    ClientWishlistSerializer,
    WishlistToggleSerializer,
)
from store.models import Wishlist, Product

logger = logging.getLogger(__name__)


# ===========================================================================
# WISHLIST MANAGEMENT
# ===========================================================================


class ClientWishlistView(generics.ListAPIView):
    """
    Returns all items currently saved in the client's wishlist.

    Validation Logic:
      - Filter: Strictly scoped to the authenticated user.
      - Join: Prefetches product images and category data for frontend rendering.

    Security:
      - Requires IsAuthenticated + IsClient.

    Status Codes:
      200 OK: Wishlist data returned.
    """

    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = ClientWishlistSerializer
    permission_classes = [IsAuthenticated, IsClient]

    def get_queryset(self):
        return (
            Wishlist.objects.filter(user=self.request.user)
            .select_related("product", "product__category")
            .order_by("-id")
        )


class ClientWishlistToggleView(generics.GenericAPIView):
    """
    Toggles the wishlist status of a specific product.

    Flow:
      - If product exists in wishlist -> DELETE (Remove).
      - If product not in wishlist -> CREATE (Add).

    Validation Logic:
      - Verifies product_id is a valid UUID and existing product.

    Security:
      - Requires IsAuthenticated + IsClient.

    Status Codes:
      200 OK: Item removed ('action': 'removed').
      201 Created: Item added ('action': 'added').
      404 Not Found: Product missing.
    """

    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = WishlistToggleSerializer
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]

        try:
            product = Product.objects.get(id=product_id)
        except (Product.DoesNotExist, ValueError):
            return error_response(
                message="Product not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = Wishlist.objects.filter(product=product, user=request.user)
        if existing.exists():
            existing.delete()
            logger.info(
                "Wishlist: removed product=%s for user=%s",
                product_id,
                request.user.email,
            )
            return success_response(
                data={"action": "removed"},
                message="Removed from wishlist.",
                status=status.HTTP_200_OK,
            )

        Wishlist.objects.create(product=product, user=request.user)
        logger.info(
            "Wishlist: added product=%s for user=%s", product_id, request.user.email
        )
        return success_response(
            data={"action": "added"},
            message="Added to wishlist.",
            status=status.HTTP_201_CREATED,
        )
