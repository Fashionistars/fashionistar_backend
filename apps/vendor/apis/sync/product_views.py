# apps/vendor/apis/sync/product_views.py
"""
Vendor Product Management — DRF Sync Views
==========================================

Handles the lifecycle of products owned by a Vendor, including creation,
modification, soft-deletion, and catalog filtering.

URL prefix: /api/v1/vendor/

Design Principles:
  - Scoping: All operations are strictly bound to the authenticated user's Vendor profile.
  - Atomicity: Product mutations (create/update) are wrapped in transactions.
  - Validation: Deep validation for nested data (specs, gallery, etc.) via serializers.
"""

import logging
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from apps.vendor.serializers.product_serializers import (
    VendorProductSerializer,
    VendorProductListSerializer,
    VendorOrderStatusSerializer
)
from store.models import Product, CartOrder

logger = logging.getLogger(__name__)


# ===========================================================================
# HELPERS
# ===========================================================================


def _get_profile_or_404(user):
    """
    Retrieves the vendor profile for the given user or raises a controlled error.
    """
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


# ===========================================================================
# PRODUCT CREATION
# ===========================================================================


class VendorProductCreateView(generics.CreateAPIView):
    """
    Creates a new product entry for the authenticated vendor.

    Flow:
      1. Validates basic product fields.
      2. Processes nested specifications, colors, sizes, and gallery.
      3. Automatically associates the product with the vendor's profile.

    Validation Logic:
      - Checks if user is a registered vendor.
      - Enforces required fields for product visibility.

    Security:
      - Requires IsAuthenticated and IsVendor.

    Status Codes:
      201 Created: Product and all related data successfully saved.
      400 Bad Request: Validation failure.
      404 Not Found: Vendor profile missing.
    """
    serializer_class = VendorProductSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            profile = _get_profile_or_404(self.request.user)
            serializer.save(vendor=profile)
            logger.info("Product created for vendor=%s", profile.pk)
        except ValueError as exc:
            from rest_framework.exceptions import NotFound
            raise NotFound(str(exc))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return success_response(
            data=serializer.data,
            message="Product created successfully.",
            status=status.HTTP_201_CREATED,
            headers=headers
        )


# ===========================================================================
# PRODUCT MODIFICATION
# ===========================================================================


class VendorProductUpdateView(generics.UpdateAPIView):
    """
    Updates an existing product's details and nested assets.

    Validation Logic:
      - Verifies the product PID belongs to the authenticated vendor.
      - Validates all updated fields against the schema.

    Security:
      - Scoped to vendor_products; cannot modify products from other vendors.

    Status Codes:
      200 OK: Update successful.
      404 Not Found: Product not found in vendor's inventory.
    """
    serializer_class = VendorProductSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_field = 'pid'
    lookup_url_kwarg = 'product_pid'

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_products.all()
        except ValueError:
            return Product.objects.none()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()
        logger.info("Product updated: pid=%s", self.kwargs.get(self.lookup_url_kwarg))

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return success_response(
            data=serializer.data,
            message="Product updated successfully."
        )


class VendorProductDeleteView(generics.DestroyAPIView):
    """
    Removes a product from the vendor's catalog.

    Security:
      - Ownership check: Uses vendor_products queryset to prevent unauthorized deletions.

    Status Codes:
      200 OK: Deletion confirmed with success message.
      404 Not Found: Target product not found.
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_field = 'pid'
    lookup_url_kwarg = 'product_pid'

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_products.all()
        except ValueError:
            return Product.objects.none()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(
            message="Product deleted successfully.",
            status=status.HTTP_200_OK
        )


# ===========================================================================
# CATALOG FILTERING
# ===========================================================================


class VendorProductFilterView(generics.ListAPIView):
    """
    Provides filtered and sorted listings of a vendor's inventory.

    Query Params:
      status (str): published, draft, disabled, in-review.
      ordering (str): latest, oldest.
      q (str): Keyword search in title.

    Status Codes:
      200 OK: Returns matching product list.
    """
    serializer_class = VendorProductListSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
        except ValueError:
            return Product.objects.none()

        status_filter = self.request.query_params.get("status", "").strip()
        ordering = self.request.query_params.get("ordering", "latest").strip()
        query = self.request.query_params.get("q", "").strip()

        qs = profile.vendor_products.all()
        if query:
            qs = qs.filter(title__icontains=query)

        valid_statuses = {"published", "draft", "disabled", "in-review"}
        if status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        if ordering == "oldest":
            qs = qs.order_by("date")
        else:
            qs = qs.order_by("-date")
        return qs


# ===========================================================================
# ORDER STATUS MANAGEMENT
# ===========================================================================


class VendorOrderStatusUpdateView(generics.UpdateAPIView):
    """
    Allows vendors to advance order fulfillment states.

    Validation Logic:
      - Permitted transitions: Pending -> Processing -> Shipped -> Fulfilled.
      - Payment status is handled by the gateway and remains immutable here.

    Status Codes:
      200 OK: State transition successful.
      400 Bad Request: Invalid status value provided.
    """
    serializer_class = VendorOrderStatusSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_url_kwarg = 'order_id'
    lookup_field = 'pk'

    def get_queryset(self):
        try:
            profile = _get_profile_or_404(self.request.user)
            return profile.vendor_orders.all()
        except ValueError:
            return CartOrder.objects.none()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(
            data=serializer.data,
            message="Order status updated successfully."
        )

