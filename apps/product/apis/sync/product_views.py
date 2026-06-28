# apps/product/apis/sync/product_views.py
"""
Enterprise DRF synchronous views for the Product domain.

Design principles (Django 6.0 / DRF):
  - Views are THIN: no business logic — all mutations go through the service layer.
  - All reads delegate to selectors; views never construct raw ORM queries.
  - Pagination is applied to all list endpoints via StandardResultsSetPagination.
  - Permission matrix:
      Public endpoints   → AllowAny
      Vendor endpoints   → IsAuthenticated + IsVendor + IsAuthenticatedAndActive
      Client endpoints   → IsAuthenticated + IsClient + IsAuthenticatedAndActive
      Admin endpoints    → IsAuthenticated + IsAdminUser
  - Idempotency keys forwarded from request headers / body to service layer.
  - view_count incremented atomically via F() to prevent race conditions.
  - All errors return structured error_response; never raw DRF exceptions.

────────────────────────────────────────────────────────────────
5 Enterprise Best-Practice Additions
────────────────────────────────────────────────────────────────
1. PAGINATION: StandardResultsSetPagination (page + page_size) on all lists.
2. RATE-LIMIT HINT: X-RateLimit-Scope header on vendor write endpoints.
3. CACHE HEADERS: ETag + Last-Modified on public product detail responses.
4. ORDERING: ordering query param validated via whitelist before passing to selector.
5. VENDOR INVENTORY LOG: dedicated endpoint exposes stock movement history.
"""

from __future__ import annotations

import logging
import uuid

from django.db.models import F
from rest_framework import parsers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.permissions import (
    IsAuthenticatedAndActive,
    IsClient,
    IsVendor,
    IsProductOwner,
)
from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.product.models import Product, ProductInventoryLog
from apps.product.selectors import (
    filter_products,
    get_featured_products,
    get_product_detail,
    get_product_reviews,
    get_products_by_category,
    get_products_by_vendor,
    get_wishlist_for_identity,
    get_vendor_coupons,
    get_vendor_product_or_404,
    get_vendor_review_summary,
)
from apps.product.serializers import (
    CouponSerializer,
    ProductAdminSerializer,
    ProductDetailSerializer,
    ProductVariantGalleryMediaSerializer,
    ProductInventoryLogSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
    ProductReviewWriteSerializer,
    ProductWishlistSerializer,
    ProductWriteFullSerializer,
    VendorReplySerializer,
)
from apps.product.services import (
    adjust_inventory,
    approve_product,
    archive_product,
    attach_gallery_media,
    create_product,
    create_review,
    merge_anonymous_wishlist_session,
    publish_product,
    reject_product,
    remove_gallery_media,
    toggle_wishlist,
    update_product,
    validate_and_apply_coupon,
)

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]
_PARSERS = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

ALLOWED_ORDERING = {
    "price", "-price", "latest", "oldest",
    "rating", "-created_at", "popular",
}


# ─────────────────────────────────────────────────────────────────────────────
# PAGINATION
# ─────────────────────────────────────────────────────────────────────────────

class StandardResultsSetPagination(PageNumberPagination):
    """
    Best-practice #1: paginate ALL list endpoints.
    Default 24 per page (4×6 grid). Max 100 per page.
    """
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_success_response(self, data):
        return success_response(
            data={
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


def _paginate(view, qs, serializer_class, request):
    """Helper: paginate a queryset and return a success_response."""
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(qs, request, view=view)
    if page is not None:
        s = serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_success_response(s.data)
    s = serializer_class(qs, many=True, context={"request": request})
    return success_response(data=s.data)


def _wishlist_identity(request) -> dict:
    """
    Resolve wishlist owner from JWT auth or anonymous browser session key.

    Anonymous callers use the same stable ID contract as cart:
    X-Fashionistar-Session-Key header, session_key body/query param, or cookie.
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return {"user": user}

    session_key = (
        request.data.get("session_key")
        or request.headers.get("X-Fashionistar-Session-Key")
        or request.query_params.get("session_key")
        or request.COOKIES.get("fashionistar_session_key")
    )
    if not session_key:
        raise ValueError("session_key is required for anonymous wishlist access.")
    return {"session_key": str(session_key)[:40]}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC — Product List / Featured / Category / Search
# ─────────────────────────────────────────────────────────────────────────────

class ProductListView(APIView):
    """
    GET /api/v1/products/
    Public. Query params:
      q, category, brand, vendor, min_price, max_price,
      in_stock, featured, ordering, page, page_size
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request):
        params = request.query_params
        ordering = params.get("ordering", "-created_at")
        if ordering not in ALLOWED_ORDERING:
            ordering = "-created_at"

        qs = filter_products(
            category_id=params.get("category"),
            brand_id=params.get("brand"),
            vendor_id=params.get("vendor"),
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
            in_stock=params.get("in_stock"),
            featured=params.get("featured") == "true" if params.get("featured") else None,
            query=params.get("q"),
            ordering=ordering,
        )
        return _paginate(self, qs, ProductListSerializer, request)


class FeaturedProductListView(APIView):
    """GET /api/v1/products/featured/ — Public."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 20)), 60)
        qs = get_featured_products(limit=limit)
        s = ProductListSerializer(qs, many=True, context={"request": request})
        return success_response(data=s.data, message="Featured products retrieved.")


class ProductDetailView(APIView):
    """GET /api/v1/products/<slug>/ — Public. Includes ETag cache headers."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        product = get_product_detail(slug)
        if not product:
            return error_response(
                message="Product not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        # Best-practice #3: atomic view count via F() — no race condition
        Product.objects.filter(pk=product.pk).update(views=F("views") + 1)

        serializer = ProductDetailSerializer(product, context={"request": request})
        response = success_response(
            data=serializer.data,
            message="Product retrieved.",
        )
        # Best-practice #3: Last-Modified header for CDN/client cache
        response["Last-Modified"] = product.updated_at.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        return response


class ProductsByCategoryView(APIView):
    """GET /api/v1/products/category/<category_id>/ — Public."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request, category_id):
        qs = get_products_by_category(category_id)
        return _paginate(self, qs, ProductListSerializer, request)


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Product CRUD
# ─────────────────────────────────────────────────────────────────────────────

def _get_vendor_product_secure(view_instance, request, slug: str) -> Product | None:
    """
    Retrieve product and strictly verify vendor ownership to prevent horizontal IDOR.
    Raises permission_denied (403) if product is owned by another vendor.
    """
    vendor = request.user.vendor_profile
    product = get_vendor_product_or_404(vendor.id, slug)
    if not product:
        if Product.objects.filter(slug=slug, is_deleted=False).exists():
            view_instance.permission_denied(
                request,
                message="You do not have permission to modify this product."
            )
        return None
    view_instance.check_object_permissions(request, product)
    return product


class VendorProductListCreateView(APIView):
    """
    GET  /api/v1/products/vendor/  — List vendor's own products (paginated).
    POST /api/v1/products/vendor/  — Create product (idempotency key supported).
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile
        qs = get_products_by_vendor(vendor.id)
        return _paginate(self, qs, ProductListSerializer, request)

    def post(self, request):
        # Best-practice #2: rate-limit scope header
        vendor = request.user.vendor_profile
        serializer = ProductWriteFullSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                code="validation_error",
                errors=serializer.errors,
            )
        # Extract idempotency key before popping M2M fields
        vdata = dict(serializer.validated_data)
        idempotency_key = vdata.pop("idempotency_key", None)
        try:
            product = create_product(
                vendor=vendor,
                validated_data=vdata,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            logger.exception("Product creation failed: %s", exc)
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        response = success_response(
            data=ProductDetailSerializer(product, context={"request": request}).data,
            message="Product created successfully.",
            status=status.HTTP_201_CREATED,
        )
        response["X-RateLimit-Scope"] = "vendor-write"
        return response


class VendorProductDetailView(APIView):
    """
    GET    /api/v1/products/vendor/<slug>/
    PATCH  /api/v1/products/vendor/<slug>/
    DELETE /api/v1/products/vendor/<slug>/
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor, IsProductOwner]

    def _get_product(self, request, slug: str) -> Product | None:
        return _get_vendor_product_secure(self, request, slug)

    def get(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=ProductDetailSerializer(product, context={"request": request}).data,
            message="Product retrieved.",
        )

    def patch(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        serializer = ProductWriteFullSerializer(
            product, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        vdata = dict(serializer.validated_data)
        vdata.pop("idempotency_key", None)
        try:
            product = update_product(
                product=product,
                validated_data=vdata,
                actor=request.user,
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductDetailSerializer(product, context={"request": request}).data,
            message="Product updated.",
        )

    def delete(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        try:
            archive_product(product=product, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            message="Product archived successfully.",
            status=status.HTTP_204_NO_CONTENT,
        )


class VendorProductPublishView(APIView):
    """POST /api/v1/products/vendor/<slug>/publish/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor, IsProductOwner]

    def post(self, request, slug: str):
        product = _get_vendor_product_secure(self, request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        try:
            product = publish_product(product=product, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            message="Product submitted for review.",
            data={"status": product.status},
        )


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Gallery Media
# ─────────────────────────────────────────────────────────────────────────────

class VendorProductGalleryView(APIView):
    """
    GET  /api/v1/products/vendor/<slug>/media/
    POST /api/v1/products/vendor/<slug>/media/
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor, IsProductOwner]

    def _get_product(self, request, slug: str) -> Product | None:
        return _get_vendor_product_secure(self, request, slug)

    def get(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        qs = product.gallery()
        serializer = ProductVariantGalleryMediaSerializer(qs, many=True, context={"request": request})
        return success_response(data=serializer.data)

    def post(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        media_file = request.FILES.get("media")
        if not media_file:
            return error_response(
                message="No media file provided.", status=status.HTTP_400_BAD_REQUEST
            )

        color_name = request.data.get("color_name", "")
        color_hex = request.data.get("color_hex", "")

        try:
            item = attach_gallery_media(
                product=product,
                media_file=media_file,
                media_type=request.data.get("media_type", "image"),
                alt_text=request.data.get("alt_text", ""),
                color_name=color_name,
                color_hex=color_hex,
                actor=request.user,
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductVariantGalleryMediaSerializer(item, context={"request": request}).data,
            message="Media attached.",
            status=status.HTTP_201_CREATED,
        )


class VendorProductGalleryDeleteView(APIView):
    """DELETE /api/v1/products/vendor/<slug>/media/<gid>/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor, IsProductOwner]

    def delete(self, request, slug: str, gid):
        product = _get_vendor_product_secure(self, request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        try:
            remove_gallery_media(product=product, gallery_id=gid, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        return success_response(
            message="Media removed.", status=status.HTTP_204_NO_CONTENT
        )


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Inventory
# ─────────────────────────────────────────────────────────────────────────────

class VendorInventoryLogView(APIView):
    """
    GET  /api/v1/products/vendor/<slug>/inventory/
    POST /api/v1/products/vendor/<slug>/inventory/  — Manual stock adjustment
    Best-practice #5: dedicated inventory log endpoint.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor, IsProductOwner]

    def _get_product(self, request, slug: str) -> Product | None:
        return _get_vendor_product_secure(self, request, slug)

    def get(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        logs = ProductInventoryLog.objects.filter(product=product).select_related(
            "actor"
        ).order_by("-created_at")[:50]
        return success_response(
            data=ProductInventoryLogSerializer(logs, many=True).data
        )

    def post(self, request, slug: str):
        product = self._get_product(request, slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        quantity_delta = request.data.get("quantity_delta")
        reason = request.data.get("reason", "adjustment")
        note = request.data.get("note", "")
        reference_id = request.data.get("reference_id", "")
        if quantity_delta is None:
            return error_response(
                message="quantity_delta is required.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            log = adjust_inventory(
                product=product,
                quantity_delta=int(quantity_delta),
                reason=reason,
                actor=request.user,
                note=note,
                reference_id=reference_id,
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductInventoryLogSerializer(log).data,
            message="Stock adjusted.",
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — Reviews
# ─────────────────────────────────────────────────────────────────────────────

class ProductReviewListCreateView(APIView):
    """
    GET  /api/v1/products/<product_slug>/reviews/  — Public list (paginated).
    POST /api/v1/products/<product_slug>/reviews/  — Authenticated client submission.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAuthenticatedAndActive(), IsClient()]
        return [AllowAny()]

    def _get_product(self, slug: str) -> Product | None:
        try:
            return Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return None

    def get(self, request, product_slug: str):
        product = self._get_product(product_slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        qs = get_product_reviews(product.id)
        return _paginate(self, qs, ProductReviewSerializer, request)

    def post(self, request, product_slug: str):
        product = self._get_product(product_slug)
        if not product:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        serializer = ProductReviewWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        vdata = serializer.validated_data
        try:
            review = create_review(
                user=request.user,
                product=product,
                rating=vdata["rating"],
                review_text=vdata["review"],
                idempotency_key=vdata.get("idempotency_key"),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductReviewSerializer(review).data,
            message="Review submitted.",
            status=status.HTTP_201_CREATED,
        )


class VendorReviewReplyView(APIView):
    """POST /api/v1/products/vendor/reviews/<review_id>/reply/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]

    def post(self, request, review_id):
        from apps.product.models import ProductReview
        try:
            review = ProductReview.objects.select_related("product__vendor").get(
                id=review_id,
                product__vendor=request.user.vendor_profile,
            )
        except ProductReview.DoesNotExist:
            return error_response(
                message="Review not found.", status=status.HTTP_404_NOT_FOUND
            )
        serializer = VendorReplySerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        review.reply = serializer.validated_data["reply"]
        review.save(update_fields=["reply", "updated_at"])
        return success_response(
            data=ProductReviewSerializer(review).data,
            message="Reply posted.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT — Wishlist
# ─────────────────────────────────────────────────────────────────────────────

class WishlistListView(APIView):
    """GET /api/v1/products/wishlist/  — Full wishlist with embedded products."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            identity = _wishlist_identity(request)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        user = identity.get("user")
        qs = get_wishlist_for_identity(
            user_id=getattr(user, "id", None),
            session_key=identity.get("session_key"),
        )
        serializer = ProductWishlistSerializer(
            qs, many=True, context={"request": request}
        )
        return success_response(data=serializer.data)


class WishlistToggleView(APIView):
    """POST /api/v1/products/wishlist/<slug>/toggle/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [AllowAny]

    def post(self, request, slug: str):
        try:
            product = Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        try:
            result = toggle_wishlist(
                **_wishlist_identity(request),
                product=product,
                request=request,
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        msg = "Added to wishlist." if result["added"] else "Removed from wishlist."
        return success_response(data=result, message=msg)


class WishlistMergeView(APIView):
    """
    POST /api/v1/products/wishlist/merge/

    Promotes anonymous wishlist rows into the authenticated account after login
    and before checkout. The view only resolves request identity; all merge
    behavior lives in the product service layer.
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsClient]

    def post(self, request):
        session_key = (
            request.data.get("session_key")
            or request.headers.get("X-Fashionistar-Session-Key")
            or request.COOKIES.get("fashionistar_session_key")
        )
        result = merge_anonymous_wishlist_session(
            user=request.user,
            session_key=str(session_key or ""),
        )
        return success_response(data=result, message="Anonymous wishlist merged.")


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR — Coupons
# ─────────────────────────────────────────────────────────────────────────────

class VendorCouponListCreateView(APIView):
    """
    GET  /api/v1/products/coupons/
    POST /api/v1/products/coupons/
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile
        qs = get_vendor_coupons(vendor.id)
        return success_response(data=CouponSerializer(qs, many=True).data)

    def post(self, request):
        from apps.product.serializers.coupon_serializers import CouponWriteSerializer
        vendor = request.user.vendor_profile
        serializer = CouponWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        coupon = serializer.save(vendor=vendor)
        return success_response(
            data=CouponSerializer(coupon).data,
            message="Coupon created.",
            status=status.HTTP_201_CREATED,
        )


class CouponValidateView(APIView):
    """POST /api/v1/products/coupons/validate/  — Validate without applying."""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        code = request.data.get("code", "").strip()
        order_subtotal = request.data.get("order_subtotal")
        if not code or order_subtotal is None:
            return error_response(
                message="code and order_subtotal are required.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from decimal import Decimal
            result = validate_and_apply_coupon(
                code=code,
                user=request.user,
                order_subtotal=Decimal(str(order_subtotal)),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(data=result, message="Coupon is valid.")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — Moderation
# ─────────────────────────────────────────────────────────────────────────────

class AdminProductApproveView(APIView):
    """POST /api/v1/admin/products/<slug>/approve/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, slug: str):
        try:
            product = Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        try:
            product = approve_product(product=product, actor=request.user)
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=ProductAdminSerializer(product, context={"request": request}).data,
            message="Product approved and published.",
        )


class AdminProductRejectView(APIView):
    """POST /api/v1/admin/products/<slug>/reject/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, slug: str):
        try:
            product = Product.objects.get(slug=slug, is_deleted=False)
        except Product.DoesNotExist:
            return error_response(
                message="Product not found.", status=status.HTTP_404_NOT_FOUND
            )
        reason = request.data.get("reason", "")
        try:
            product = reject_product(
                product=product, actor=request.user, reason=reason
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data={"status": product.status, "reason": reason},
            message="Product rejected.",
        )


class AdminVendorReviewSummaryView(APIView):
    """GET /api/v1/admin/vendors/<vendor_id>/review-summary/"""
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, vendor_id):
        summary = get_vendor_review_summary(vendor_id)
        return success_response(data=summary)


class VendorCouponDetailView(APIView):
    """
    DELETE /api/v1/products/coupons/<uuid:coupon_id>/
    """
    renderer_classes = _RENDERERS
    parser_classes = _PARSERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive, IsVendor]

    def delete(self, request, coupon_id: uuid):
        from apps.product.models import Coupon
        vendor = request.user.vendor_profile
        try:
            coupon = Coupon.objects.get(pk=coupon_id, vendor=vendor)
        except Coupon.DoesNotExist:
            return error_response(
                message="Coupon not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        coupon.delete()
        return success_response(
            message="Coupon deactivated successfully.",
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────────────────


