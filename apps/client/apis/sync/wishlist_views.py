# apps/client/apis/sync/wishlist_views.py
"""Client wishlist APIs."""

import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.client.legacy_compat import LegacyCommerceUnavailable, get_legacy_store_model
from apps.client.serializers.wishlist_serializers import (
    ClientWishlistSerializer,
    WishlistToggleSerializer,
)
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


def _commerce_unavailable_response():
    return error_response(
        message="Client wishlist is temporarily unavailable while the product domain migration is completing.",
        code="commerce_domain_migration_pending",
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class ClientWishlistView(generics.GenericAPIView):
    serializer_class = ClientWishlistSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, *args, **kwargs):
        try:
            Wishlist = get_legacy_store_model("Wishlist")
        except LegacyCommerceUnavailable:
            logger.warning("ClientWishlistView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response()

        wishlist = (
            Wishlist.objects.filter(user=request.user)
            .select_related("product", "product__category")
            .order_by("-id")
        )
        serializer = self.get_serializer(wishlist, many=True)
        return success_response(
            data=serializer.data,
            message="Wishlist retrieved successfully.",
            meta={"count": wishlist.count()},
        )


class ClientWishlistToggleView(generics.GenericAPIView):
    serializer_class = WishlistToggleSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]

        try:
            Product = get_legacy_store_model("Product")
            Wishlist = get_legacy_store_model("Wishlist")
        except LegacyCommerceUnavailable:
            logger.warning("ClientWishlistToggleView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response()

        try:
            product = Product.objects.get(id=product_id)
        except ObjectDoesNotExist:
            return error_response(
                message="Product not found.",
                code="product_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = Wishlist.objects.filter(product=product, user=request.user)
        if existing.exists():
            existing.delete()
            logger.info("Wishlist: removed product=%s for user=%s", product_id, request.user.pk)
            return success_response(
                data={"action": "removed"},
                message="Removed from wishlist.",
                status=status.HTTP_200_OK,
            )

        Wishlist.objects.create(product=product, user=request.user)
        logger.info("Wishlist: added product=%s for user=%s", product_id, request.user.pk)
        return success_response(
            data={"action": "added"},
            message="Added to wishlist.",
            status=status.HTTP_201_CREATED,
        )
