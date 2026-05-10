# apps/client/apis/sync/wishlist_views.py
"""Client wishlist APIs."""

import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.product.models import ProductWishlist
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
            .prefetch_related("product__categories", "product__sub_categories")
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

        existing = ProductWishlist.objects.filter(product=product_id, user=request.user)
        if existing.exists():
            existing.delete()
            logger.info(
                "Wishlist: removed product=%s for user=%s", product_id, request.user.pk
            )
            return success_response(
                data={"action": "removed"},
                message="Removed from wishlist.",
                status=status.HTTP_200_OK,
            )

        ProductWishlist.objects.create(product=product_id, user=request.user)
        logger.info(
            "Wishlist: added product=%s for user=%s", product_id, request.user.pk
        )
        return success_response(
            data={"action": "added"},
            message="Added to wishlist.",
            status=status.HTTP_201_CREATED,
        )
