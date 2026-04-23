# apps/vendor/apis/sync/product_views.py
"""
Vendor Product Management — DRF Sync Views.

URL prefix: /api/v1/vendor/

Endpoints:
  POST   /api/v1/vendor/products/create/                 — create product
  GET    /api/v1/vendor/products/filter/                 — filter by status
  PUT    /api/v1/vendor/products/<str:product_pid>/edit/  — full update (+ nested)
  PATCH  /api/v1/vendor/products/<str:product_pid>/edit/  — partial update
  DELETE /api/v1/vendor/products/<str:product_pid>/delete/ — soft-delete

All views use DRF generics where possible.
All DB access scoped via vendor_products reverse FK (no N+1).
Nested data (specifications, colors, sizes, gallery) parsed from flat multipart keys.
"""
import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsVendor
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none

logger = logging.getLogger(__name__)


# ── Helper ─────────────────────────────────────────────────────────────────


def _get_profile_or_404(user):
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


def _parse_nested_product_data(data: dict) -> dict:
    """
    Parse flat multipart keys into structured nested lists.
    e.g. 'specifications[0][title]' → [{title: ..., content: ...}]
    """
    specifications, colors, sizes, gallery = [], [], {}, []

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
    Imports Product-related models lazily to avoid circular imports.
    """
    from apps.store.models import Color, Gallery, Size, Specification  # adjust to your store app path

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


class VendorProductCreateView(generics.GenericAPIView):
    """
    POST /api/v1/vendor/products/create/

    Create a new product scoped to this vendor.
    Accepts multipart/form-data with optional nested fields:
      specifications[0][title], specifications[0][content]
      colors[0][name], colors[0][color_code], colors[0][image]
      sizes[0][name], sizes[0][price]
      gallery[0][image]
    """
    permission_classes = [IsAuthenticated, IsVendor]

    @transaction.atomic
    def post(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        from apps.store.models import Product  # lazy import
        from apps.store.serializers import ProductSerializer  # lazy import

        serializer = ProductSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        product = serializer.save(vendor=profile)
        nested = _parse_nested_product_data(request.data)

        try:
            _save_nested_product_data(product, nested)
        except Exception as exc:
            logger.warning("VendorProductCreateView: nested save failed: %s", exc)

        logger.info("Product created: pid=%s vendor=%s", product.pid, profile.pk)
        return Response({
            "status": "success",
            "message": "Product created successfully.",
            "data": {"pid": str(product.pid), "title": product.title},
        }, status=status.HTTP_201_CREATED)


# ══════════════════════════════════════════════════════════════════
#  Product Update (full + partial)
# ══════════════════════════════════════════════════════════════════


class VendorProductUpdateView(generics.GenericAPIView):
    """
    PUT  /api/v1/vendor/products/<product_pid>/edit/  — full update
    PATCH /api/v1/vendor/products/<product_pid>/edit/ — partial update

    Scoped to this vendor via vendor_products reverse FK.
    Replaces all nested specs/colors/sizes/gallery on update.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def _get_product(self, profile, product_pid: str):
        try:
            return profile.vendor_products.get(pid=product_pid)
        except Exception:
            return None

    @transaction.atomic
    def _handle_update(self, request, product_pid: str, partial: bool):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        product = self._get_product(profile, product_pid)
        if product is None:
            return Response({"status": "error", "message": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        from apps.store.serializers import ProductSerializer  # lazy import

        serializer = ProductSerializer(product, data=request.data, partial=partial)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        product = serializer.save()
        nested = _parse_nested_product_data(request.data)

        try:
            _save_nested_product_data(product, nested)
        except Exception as exc:
            logger.warning("VendorProductUpdateView: nested save failed: %s", exc)

        logger.info("Product updated: pid=%s vendor=%s", product_pid, profile.pk)
        return Response({"status": "success", "message": "Product updated."})

    def put(self, request, product_pid: str):
        return self._handle_update(request, product_pid, partial=False)

    def patch(self, request, product_pid: str):
        return self._handle_update(request, product_pid, partial=True)


# ══════════════════════════════════════════════════════════════════
#  Product Delete
# ══════════════════════════════════════════════════════════════════


class VendorProductDeleteView(generics.GenericAPIView):
    """
    DELETE /api/v1/vendor/products/<product_pid>/delete/

    Hard-delete a vendor's own product.
    Scoped via vendor_products reverse FK — cannot delete another vendor's product.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    @transaction.atomic
    def delete(self, request, product_pid: str):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        try:
            product = profile.vendor_products.get(pid=product_pid)
        except Exception:
            return Response({"status": "error", "message": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        pid = str(product.pid)
        product.delete()
        logger.info("Product deleted: pid=%s vendor=%s", pid, profile.pk)
        return Response({"status": "success", "message": "Product deleted."}, status=status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════
#  Product Filter
# ══════════════════════════════════════════════════════════════════


class VendorProductFilterView(generics.GenericAPIView):
    """
    GET /api/v1/vendor/products/filter/?status=published|draft|disabled|in-review
    GET /api/v1/vendor/products/filter/?ordering=latest|oldest

    Filter + sort vendor's own products using query params.
    All status values: published, draft, disabled, in-review.
    Ordering values: latest (default), oldest.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        status_filter = request.query_params.get("status", "").strip()
        ordering = request.query_params.get("ordering", "latest").strip()

        qs = profile.vendor_products.all()

        # Status filter
        valid_statuses = {"published", "draft", "disabled", "in-review"}
        if status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        # Ordering
        qs = qs.order_by("date") if ordering == "oldest" else qs.order_by("-date")

        products = list(
            qs.values("pid", "title", "price", "stock_qty", "status", "category__name", "date")
        )
        return Response({
            "status": "success",
            "count": len(products),
            "data": products,
        })


# ══════════════════════════════════════════════════════════════════
#  Order Status Update (vendor-side)
# ══════════════════════════════════════════════════════════════════


class VendorOrderStatusUpdateView(generics.GenericAPIView):
    """
    PATCH /api/v1/vendor/orders/<int:order_id>/status/

    Update order_status for a vendor's own order.
    Allowed values: Pending, Processing, Shipped, Fulfilled, Cancelled.
    Payment status (paid/unpaid) is immutable here — managed by payment gateway.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    ALLOWED_STATUSES = {"Pending", "Processing", "Shipped", "Fulfilled", "Cancelled"}

    def patch(self, request, order_id: int):
        try:
            profile = _get_profile_or_404(request.user)
        except ValueError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("order_status", "").strip()
        if new_status not in self.ALLOWED_STATUSES:
            return Response({
                "status": "error",
                "message": f"Invalid order_status. Allowed: {sorted(self.ALLOWED_STATUSES)}",
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = profile.vendor_orders.get(pk=order_id)
        except Exception:
            return Response({"status": "error", "message": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        old_status = order.order_status
        order.order_status = new_status
        order.save(update_fields=["order_status"])

        logger.info(
            "Order %s status changed: %s → %s by vendor=%s",
            order_id, old_status, new_status, profile.pk,
        )
        return Response({
            "status": "success",
            "message": f"Order status updated to '{new_status}'.",
            "data": {"order_id": order_id, "order_status": new_status},
        })
