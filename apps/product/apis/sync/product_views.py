# apps/product/apis/sync/product_views.py
"""
DRF synchronous views for the Product domain.

All views:
  - Use CustomJSONRenderer + BrowsableAPIRenderer
  - Return success_response / error_response from apps.common.renderers
  - Use MultiPartParser + FormParser + JSONParser for media support
"""

import logging

from rest_framework import generics, status, parsers
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.common.permissions import (
    IsVendorWithProfile, IsClient, IsVerifiedUser, IsAuthenticatedAndActive,
)
from apps.product.models import Product, ProductGalleryMedia
from apps.product.serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ProductGalleryMediaSerializer,
    ProductReviewSerializer,
    ProductReviewWriteSerializer,
    CouponSerializer,
    CouponWriteSerializer,
)
from apps.product.selectors import (
    get_published_products,
    get_product_detail,
    get_featured_products,
    get_products_by_category,
    get_products_by_vendor,
    get_vendor_product_or_404,
    filter_products,
    get_product_reviews,
    get_user_wishlist,
    get_vendor_coupons,
)
from apps.product.services import (
    create_product,
    update_product,
    publish_product,
    archive_product,
    attach_gallery_media,
    remove_gallery_media,
    create_review,
    toggle_wishlist,
)

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]
_PARSERS = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC — Product List / Featured
# ─────────────────────────────────────────────────────────────────────────────

class ProductListView(APIView):
    """
    GET /api/v1/products/
    Public. Supports filters: category, brand, min_price, max_price, in_stock, featured, q.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request):
        params = request.query_params
        qs = filter_products(
            category_id=params.get("category"),
            brand_id=params.get("brand"),
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
            in_stock=params.get("in_stock"),
            featured=params.get("featured"),
            query=params.get("q"),
        )
        serializer = ProductListSerializer(qs, many=True, context={"request": request})
        return success_response(data=serializer.data, message="Products retrieved.")


class FeaturedProductListView(APIView):
    """GET /api/v1/products/featured/ — Public."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request):
        qs = get_featured_products(limit=40)
        serializer = ProductListSerializer(qs, many=True, context={"request": request})
        return success_response(data=serializer.data, message="Featured products retrieved.")


class ProductDetailView(APIView):
    """GET /api/v1/products/<slug>/ — Public."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request, slug):
        product = get_product_detail(slug)
        if not product:
            return error_response(
                message="Product not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        # Increment view count (fire-and-forget)
        try:
            Product.objects.filter(pk=product.pk).update(views=product.views + 1)
        except Exception:
            pass
        serializer = ProductDetailSerializer(product, context={"request": request})
        return success_response(data=serializer.data, message="Product retrieved.")


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Product CRUD
# ─────────────────────────────────────────────────────────────────────────────

class VendorProductListCreateView(APIView):
    """
    GET  /api/v1/products/vendor/  — List vendor's own products.
    POST /api/v1/products/vendor/  — Create a new product (status=DRAFT).
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendorWithProfile]

    def get(self, request):
        vendor = request.user.vendor_profile
        qs = get_products_by_vendor(vendor.id)
        serializer = ProductListSerializer(qs, many=True, context={"request": request})
        return success_response(data=serializer.data, message="Vendor products retrieved.")

    def post(self, request):
        vendor = request.user.vendor_profile
        serializer = ProductWriteSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                code="validation_error",
                errors=serializer.errors,
            )
        try:
            product = create_product(vendor=vendor, validated_data=serializer.validated_data)
        except Exception as exc:
            logger.exception("Product creation failed: %s", exc)
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return success_response(
            data=ProductDetailSerializer(product, context={"request": request}).data,
            message="Product created successfully.",
            status=status.HTTP_201_CREATED,
        )


class VendorProductDetailView(APIView):
    """
    GET    /api/v1/products/vendor/<slug>/  — View own product.
    PATCH  /api/v1/products/vendor/<slug>/  — Update.
    DELETE /api/v1/products/vendor/<slug>/  — Soft-delete.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendorWithProfile]

    def _get_product(self, request, slug):
        vendor = request.user.vendor_profile
        product = get_vendor_product_or_404(vendor.id, slug)
        if not product:
            return None
        return product

    def get(self, request, slug):
        product = self._get_product(request, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(
            data=ProductDetailSerializer(product, context={"request": request}).data,
            message="Product retrieved.",
        )

    def patch(self, request, slug):
        product = self._get_product(request, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        serializer = ProductWriteSerializer(
            product, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            product = update_product(
                product=product,
                validated_data=serializer.validated_data,
                actor=request.user,
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductDetailSerializer(product, context={"request": request}).data,
            message="Product updated.",
        )

    def delete(self, request, slug):
        product = self._get_product(request, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        try:
            archive_product(product=product, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(message="Product archived.", status=status.HTTP_204_NO_CONTENT)


class VendorProductPublishView(APIView):
    """POST /api/v1/products/vendor/<slug>/publish/ — Submit for review."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendorWithProfile]

    def post(self, request, slug):
        vendor = request.user.vendor_profile
        product = get_vendor_product_or_404(vendor.id, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        try:
            product = publish_product(product=product, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(message="Product submitted for review.", data={"status": product.status})


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Gallery Media
# ─────────────────────────────────────────────────────────────────────────────

class VendorProductGalleryView(APIView):
    """
    GET    /api/v1/products/vendor/<slug>/media/  — List gallery.
    POST   /api/v1/products/vendor/<slug>/media/  — Upload media.
    DELETE /api/v1/products/vendor/<slug>/media/<gid>/ — Remove media.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendorWithProfile]

    def _get_product(self, request, slug):
        vendor = request.user.vendor_profile
        return get_vendor_product_or_404(vendor.id, slug)

    def get(self, request, slug):
        product = self._get_product(request, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        serializer = ProductGalleryMediaSerializer(
            product.gallery.all(), many=True, context={"request": request}
        )
        return success_response(data=serializer.data)

    def post(self, request, slug):
        product = self._get_product(request, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        media_file = request.FILES.get("media")
        if not media_file:
            return error_response(message="No media file provided.", status=status.HTTP_400_BAD_REQUEST)
        try:
            item = attach_gallery_media(
                product=product,
                media_file=media_file,
                media_type=request.data.get("media_type", "image"),
                alt_text=request.data.get("alt_text", ""),
                actor=request.user,
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductGalleryMediaSerializer(item).data,
            message="Media attached.",
            status=status.HTTP_201_CREATED,
        )


class VendorProductGalleryDeleteView(APIView):
    """DELETE /api/v1/products/vendor/<slug>/media/<gid>/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendorWithProfile]

    def delete(self, request, slug, gid):
        vendor = request.user.vendor_profile
        product = get_vendor_product_or_404(vendor.id, slug)
        if not product:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        try:
            remove_gallery_media(product=product, gallery_id=gid, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        return success_response(message="Media removed.", status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — Reviews
# ─────────────────────────────────────────────────────────────────────────────

class ProductReviewListCreateView(APIView):
    """
    GET  /api/v1/products/<slug>/reviews/  — Public review list.
    POST /api/v1/products/<slug>/reviews/  — Authenticated client submit.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAuthenticatedAndActive(), IsClient()]
        return [AllowAny()]

    def get(self, request, slug):
        try:
            product = Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        qs = get_product_reviews(product.id)
        serializer = ProductReviewSerializer(qs, many=True)
        return success_response(data=serializer.data)

    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        serializer = ProductReviewWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation error.", status=status.HTTP_400_BAD_REQUEST, errors=serializer.errors)
        try:
            review = create_review(
                user=request.user,
                product=product,
                rating=serializer.validated_data["rating"],
                review_text=serializer.validated_data["review"],
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductReviewSerializer(review).data,
            message="Review submitted.",
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — Wishlist
# ─────────────────────────────────────────────────────────────────────────────

class WishlistListView(APIView):
    """GET /api/v1/products/wishlist/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsClient]

    def get(self, request):
        qs = get_user_wishlist(request.user.id)
        data = ProductListSerializer(
            [w.product for w in qs], many=True, context={"request": request}
        ).data
        return success_response(data=data)


class WishlistToggleView(APIView):
    """POST /api/v1/products/wishlist/<slug>/toggle/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsClient]

    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(message="Product not found.", status=status.HTTP_404_NOT_FOUND)
        result = toggle_wishlist(user=request.user, product=product)
        msg = "Added to wishlist." if result["added"] else "Removed from wishlist."
        return success_response(data=result, message=msg)


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Coupons
# ─────────────────────────────────────────────────────────────────────────────

class VendorCouponListCreateView(APIView):
    """
    GET  /api/v1/products/coupons/  — List vendor coupons.
    POST /api/v1/products/coupons/  — Create coupon.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendorWithProfile]

    def get(self, request):
        vendor = request.user.vendor_profile
        qs = get_vendor_coupons(vendor.id)
        return success_response(data=CouponSerializer(qs, many=True).data)

    def post(self, request):
        vendor = request.user.vendor_profile
        serializer = CouponWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation error.", status=status.HTTP_400_BAD_REQUEST, errors=serializer.errors)
        coupon = serializer.save(vendor=vendor)
        return success_response(
            data=CouponSerializer(coupon).data,
            message="Coupon created.",
            status=status.HTTP_201_CREATED,
        )
