# apps/client/apis/sync/review_views.py
"""
Client Review API — DRF Sync Views.

Migrated & modernized from legacy customer/reviews.py.
Public review list (AllowAny) + authenticated create (IsClient).

URL prefix: /api/v1/client/ and /api/v1/home/

Endpoints:
  GET  /api/v1/home/reviews/<uuid:product_id>/  — public product reviews
  POST /api/v1/client/reviews/create/           — create review (client only)
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsClient

logger = logging.getLogger(__name__)


class ProductReviewListView(APIView):
    """
    GET /api/v1/home/reviews/<uuid:product_id>/

    Public endpoint: list all ACTIVE (approved) reviews for a product.
    No authentication required — used for product detail pages.
    Optimised with select_related to avoid N+1 on user/profile.
    """
    permission_classes = [AllowAny]

    def get(self, request, product_id):
        from store.models import Product, Review
        from store.serializers import ReviewSerializer

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"status": "error", "message": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        reviews = (
            Review.objects
            .filter(product=product, active=True)
            .select_related("product", "user")
            .order_by("-date")
        )
        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            "status": "success",
            "count": reviews.count(),
            "data": serializer.data,
        })


class ClientReviewCreateView(APIView):
    """
    POST /api/v1/client/reviews/create/

    Body: { "product_id": "<uuid>", "rating": 5, "review": "Great product!" }

    Create a product review as an authenticated client.
    Validates:
      - product exists
      - rating is within 1–5
    One review per user per product is enforced by unique_together in the
    Review model (if configured). If not, duplicates are allowed — front-end
    should guard against re-submitting.
    """
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        product_id = request.data.get("product_id")
        rating = request.data.get("rating")
        review_text = request.data.get("review", "")

        if not product_id:
            return Response(
                {"status": "error", "message": "product_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rating = int(rating)
            if not (1 <= rating <= 5):
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"status": "error", "message": "rating must be an integer between 1 and 5."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from store.models import Product, Review

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"status": "error", "message": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        Review.objects.create(
            user=request.user,
            product=product,
            rating=rating,
            review=review_text,
        )
        logger.info(
            "Review created: product=%s rating=%d user=%s",
            product_id, rating, request.user.email,
        )
        return Response(
            {"status": "success", "message": "Review submitted successfully."},
            status=status.HTTP_201_CREATED,
        )
