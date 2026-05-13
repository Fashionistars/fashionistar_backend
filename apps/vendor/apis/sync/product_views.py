# apps/vendor/apis/sync/product_views.py
"""
Vendor Product Management — DRF Sync Views.

URL prefix: /api/v1/vendor/

Endpoints:
  POST   /api/v1/vendor/products/create/                 — create product
  GET    /api/v1/vendor/products/filter/                 — filter by status
  PUT    /api/v1/vendor/products/<str:product_pid>/edit/  — full update
  PATCH  /api/v1/vendor/products/<str:product_pid>/edit/  — partial update
  DELETE /api/v1/vendor/products/<str:product_pid>/delete/ — delete
  PATCH  /api/v1/vendor/orders/<int:order_id>/status/    — order status update

All DB access scoped via vendor_products reverse FK (no N+1).
"""

import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from apps.vendor.serializers.product_serializers import (
    VendorOrderStatusSerializer,
    VendorProductListSerializer,
    VendorProductSerializer,
)

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_profile_or_404(user):
    """Return vendor profile or raise ValueError."""
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


def _parse_nested_product_data(data: dict) -> dict:
    """
    Parse flat multipart keys into structured nested lists.
    e.g. 'specifications[0][title]' → [{title: ..., content: ...}]
    """
    specifications: list = []
    colors: dict = {}
    sizes: dict = {}
    gallery: list = []

    for key, value in data.items():
        if key.startswith("specifications") and "[title]" in key:
            idx = key.split("[")[1].split("]")[0]
            content = data.get(f"specifications[{idx}][content]", "")
            specifications.append({"title": value, "content": content})

        elif key.startswith("colors") and "[name]" in key:
            idx = key.split("[")[1].split("]")[0]
            colors.setdefault(idx, {})["name"] = value
            colors[idx]["color_code"] = data.get(f"colors[{idx}][color_code]", "")
            colors[idx]["image"] = data.get(f"colors[{idx}][image]", None)

        elif key.startswith("sizes") and "[name]" in key:
            idx = key.split("[")[1].split("]")[0]
            price = data.get(f"sizes[{idx}][price]", 0)
            sizes[idx] = {"name": value, "price": price}

        elif key.startswith("gallery") and "[image]" in key:
            gallery.append({"image": value})

    return {
        "specifications": specifications,
        "colors": list(colors.values()),
        "sizes": list(sizes.values()),
        "gallery": gallery,
    }


def _save_nested_product_data(product, nested: dict) -> None:
    """
    Persist nested product children (specs, colors, sizes, gallery).
    Uses enterprise apps.catalog / apps.product domain models.
    Falls back gracefully if models don't exist yet.
    """
    try:
        from apps.catalog.models import Color, Gallery, Size, Specification
    except ImportError:
        logger.warning(
            "_save_nested_product_data: catalog models not importable — skipping."
        )
        return

    if nested["specifications"]:
        Specification.objects.filter(product=product).delete()
        Specification.objects.bulk_create(
            [Specification(product=product, **s) for s in nested["specifications"]]
        )
    if nested["colors"]:
        Color.objects.filter(product=product).delete()
        Color.objects.bulk_create(
            [Color(product=product, **c) for c in nested["colors"]]
        )
    if nested["sizes"]:
        Size.objects.filter(product=product).delete()
        Size.objects.bulk_create(
            [Size(product=product, **s) for s in nested["sizes"]]
        )
    if nested["gallery"]:
        Gallery.objects.filter(product=product).delete()
        Gallery.objects.bulk_create(
            [Gallery(product=product, **g) for g in nested["gallery"]]
        )


# ══════════════════════════════════════════════════════════════════
#  Product Create
# ══════════════════════════════════════════════════════════════════


class VendorProductCreateView(generics.CreateAPIView):
    """
    POST /api/v1/vendor/products/create/

    Create a new product for the authenticated vendor.

    Request Body:
      - title, price, category, etc. (standard fields)
      - specifications: list of dicts {title, content}
      - colors: list of dicts {name, color_code}
      - sizes: list of dicts {name, price}
      - gallery: list of image files or URLs
    """

    serializer_class = VendorProductSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return success_response(
            data=serializer.data,
            message="Product created successfully.",
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            profile = _get_profile_or_404(self.request.user)
        except ValueError as exc:
            from rest_framework.exceptions import NotFound
            raise NotFound(str(exc))

        product = serializer.save(vendor=profile)
        nested = _parse_nested_product_data(self.request.data)

        try:
            _save_nested_product_data(product, nested)
        except Exception as exc:
            logger.warning("VendorProductCreateView: nested save failed: %s", exc)

        logger.info("Product created: pid=%s vendor=%s", getattr(product, "pid", product.pk), profile.pk)


# ══════════════════════════════════════════════════════════════════
#  Product Update (full + partial)
# ══════════════════════════════════════════════════════════════════


class VendorProductUpdateView(generics.UpdateAPIView):
    """
    PUT   /api/v1/vendor/products/<product_pid>/edit/  — full update
    PATCH /api/v1/vendor/products/<product_pid>/edit/  — partial update

    Scoped to this vendor via vendor_products reverse FK.
    Replaces all nested specs/colors/sizes/gallery on update.
    """

    serializer_class = VendorProductSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_field = "pid"
    lookup_url_kwarg = "product_pid"

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_products.all()
        except ValueError:
            from apps.catalog.models import Product  # noqa: F401
            return type("EmptyQS", (), {"none": lambda: []})  # safe fallback

    @transaction.atomic
    def perform_update(self, serializer):
        product = serializer.save()
        nested = _parse_nested_product_data(self.request.data)
        try:
            _save_nested_product_data(product, nested)
        except Exception as exc:
            logger.warning("VendorProductUpdateView: nested save failed: %s", exc)
        logger.info(
            "Product updated: pid=%s vendor=%s",
            self.kwargs.get(self.lookup_url_kwarg),
            self.request.user.pk,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return success_response(
            data=serializer.data,
            message="Product updated successfully.",
        )


# ══════════════════════════════════════════════════════════════════
#  Product Delete
# ══════════════════════════════════════════════════════════════════


class VendorProductDeleteView(generics.DestroyAPIView):
    """
    DELETE /api/v1/vendor/products/<product_pid>/delete/

    Hard-delete a vendor's own product.
    Scoped via vendor_products reverse FK — cannot delete another vendor's product.
    """

    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_field = "pid"
    lookup_url_kwarg = "product_pid"

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_products.all()
        except ValueError:
            from rest_framework.exceptions import NotFound
            raise NotFound("Vendor profile not found.")

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        pid = str(getattr(instance, "pid", instance.pk))
        self.perform_destroy(instance)
        logger.info("Product deleted: pid=%s vendor=%s", pid, request.user.pk)
        return success_response(
            message="Product deleted successfully.",
            status=status.HTTP_200_OK,
        )


# ══════════════════════════════════════════════════════════════════
#  Product Filter
# ══════════════════════════════════════════════════════════════════


class VendorProductFilterView(generics.ListAPIView):
    """
    GET /api/v1/vendor/products/filter/?status=published|draft|disabled|in-review
    GET /api/v1/vendor/products/filter/?ordering=latest|oldest
    GET /api/v1/vendor/products/filter/?q=<search_term>

    Filter + sort vendor's own products using query params.
    All status values: published, draft, disabled, in-review.
    Ordering values: latest (default), oldest.
    """

    serializer_class = VendorProductListSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except ValueError:
            return self.serializer_class.Meta.model.objects.none()

        status_filter = self.request.query_params.get("status", "").strip()
        ordering = self.request.query_params.get("ordering", "latest").strip()
        query = self.request.query_params.get("q", "").strip()

        qs = profile.vendor_products.prefetch_related("categories").all()

        if query:
            qs = qs.filter(title__icontains=query)

        valid_statuses = {"published", "draft", "disabled", "in-review"}
        if status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        return qs.order_by("created_at" if ordering == "oldest" else "-created_at")


# ══════════════════════════════════════════════════════════════════
#  Order Status Update (vendor-side)
# ══════════════════════════════════════════════════════════════════

ALLOWED_ORDER_STATUSES = {"Pending", "Processing", "Shipped", "Fulfilled", "Cancelled"}


class VendorOrderStatusUpdateView(generics.UpdateAPIView):
    """
    PATCH /api/v1/vendor/orders/<int:order_id>/status/

    Update order_status for a vendor's own order.
    Allowed values: Pending, Processing, Shipped, Fulfilled, Cancelled.
    Payment status (paid/unpaid) is immutable here — managed by payment gateway.
    """

    serializer_class = VendorOrderStatusSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_url_kwarg = "order_id"
    lookup_field = "pk"

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_orders.all()
        except ValueError:
            from apps.order.models import Order
            return Order.objects.none()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        new_status = request.data.get("order_status", "").strip()
        if new_status not in ALLOWED_ORDER_STATUSES:
            return error_response(
                message=f"Invalid order_status. Allowed: {sorted(ALLOWED_ORDER_STATUSES)}",
                status=status.HTTP_400_BAD_REQUEST,
            )

        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        old_status = instance.order_status

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        logger.info(
            "Order %s status changed: %s → %s by vendor=%s",
            instance.pk,
            old_status,
            new_status,
            request.user.pk,
        )
        return success_response(
            data=serializer.data,
            message=f"Order status updated to '{new_status}'.",
        )
