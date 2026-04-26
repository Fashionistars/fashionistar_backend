# apps/client/apis/sync/review_views.py
"""Client review APIs."""

import logging

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.client.legacy_compat import LegacyCommerceUnavailable, get_legacy_store_model
from apps.client.serializers.review_serializers import ClientReviewSerializer
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


def _commerce_unavailable_response():
    return error_response(
        message="Product reviews are temporarily unavailable while the product domain migration is completing.",
        code="commerce_domain_migration_pending",
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class ProductReviewListView(generics.GenericAPIView):
    serializer_class = ClientReviewSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, product_id: str, *args, **kwargs):
        try:
            Review = get_legacy_store_model("Review")
        except LegacyCommerceUnavailable:
            logger.warning("ProductReviewListView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response()

        reviews = (
            Review.objects.filter(product_id=product_id, active=True)
            .select_related("product", "user", "user__profile")
            .order_by("-date")
        )
        serializer = self.get_serializer(reviews, many=True)
        return success_response(
            data=serializer.data,
            message="Reviews retrieved successfully.",
        )


class ClientReviewCreateView(generics.GenericAPIView):
    serializer_class = ClientReviewSerializer
    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            Review = get_legacy_store_model("Review")
        except LegacyCommerceUnavailable:
            logger.warning("ClientReviewCreateView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response()

        review = Review.objects.create(
            user=request.user,
            product_id=serializer.validated_data["product_id"],
            review=serializer.validated_data["review"],
            rating=serializer.validated_data["rating"],
        )
        output_serializer = self.get_serializer(review)
        logger.info(
            "Review created: product=%s rating=%s user=%s",
            serializer.validated_data["product_id"],
            serializer.validated_data["rating"],
            request.user.pk,
        )
        return success_response(
            data=output_serializer.data,
            message="Review submitted successfully.",
            status=status.HTTP_201_CREATED,
        )
