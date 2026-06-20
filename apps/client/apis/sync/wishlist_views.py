# apps/client/apis/sync/wishlist_views.py
"""Client wishlist APIs."""

import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.product.models import Product, ProductWishlist
from apps.product.services import toggle_wishlist
from apps.client.serializers.wishlist_serializers import (
    ClientWishlistSerializer,
    WishlistToggleSerializer,
)
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


class ClientWishlistView(generics.GenericAPIView):
    serializer_class = ClientWishlistSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, *args, **kwargs):
        wishlist = (
            ProductWishlist.objects.filter(user=request.user)
            .select_related("product")
            .prefetch_related("product__categories")
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
        product = Product.objects.filter(pk=product_id, is_deleted=False).first()
        if not product:
            return error_response(
                message="Product not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        result = toggle_wishlist(user=request.user, product=product, request=request)
        logger.info(
            "Wishlist: %s product=%s for user=%s",
            "added" if result["added"] else "removed",
            product_id,
            request.user.pk,
        )
        return success_response(
            data={"action": "added" if result["added"] else "removed"},
            message="Added to wishlist." if result["added"] else "Removed from wishlist.",
            status=status.HTTP_201_CREATED if result["added"] else status.HTTP_200_OK,
        )
