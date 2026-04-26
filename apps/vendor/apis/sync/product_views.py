# apps/vendor/apis/sync/product_views.py
"""Vendor product management APIs."""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.vendor.legacy_compat import LegacyCommerceUnavailable, get_legacy_store_model
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from apps.vendor.serializers.product_serializers import (
    VendorOrderStatusSerializer,
    VendorProductListSerializer,
    VendorProductSerializer,
)

logger = logging.getLogger(__name__)


def _get_profile_or_404(user):
    profile = get_vendor_profile_or_none(user)
    if profile is None:
        raise ValueError("Vendor profile not found.")
    return profile


def _commerce_unavailable_response(message: str):
    return error_response(
        message=message,
        code="commerce_domain_migration_pending",
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class VendorProductCreateView(generics.GenericAPIView):
    serializer_class = VendorProductSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
            Product = get_legacy_store_model("Product")
        except ValueError as exc:
            return error_response(
                message=str(exc),
                code="vendor_profile_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )
        except LegacyCommerceUnavailable:
            logger.warning("VendorProductCreateView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response(
                "Vendor product creation is temporarily unavailable while the product domain migration is completing."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = Product.objects.create(vendor=profile, **serializer.validated_data)
        output_serializer = self.get_serializer(product)
        logger.info("Product created for vendor=%s", profile.pk)
        return success_response(
            data=output_serializer.data,
            message="Product created successfully.",
            status=status.HTTP_201_CREATED,
        )


class VendorProductUpdateView(generics.GenericAPIView):
    serializer_class = VendorProductSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @transaction.atomic
    def patch(self, request, product_pid: str, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
            get_legacy_store_model("Product")
        except ValueError as exc:
            return error_response(
                message=str(exc),
                code="vendor_profile_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )
        except LegacyCommerceUnavailable:
            logger.warning("VendorProductUpdateView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response(
                "Vendor product updates are temporarily unavailable while the product domain migration is completing."
            )

        try:
            product = profile.vendor_products.get(pid=product_pid)
        except ObjectDoesNotExist:
            return error_response(
                message="Product not found.",
                code="product_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for attr, value in serializer.validated_data.items():
            setattr(product, attr, value)
        product.save()
        logger.info("Product updated: pid=%s", product_pid)
        return success_response(
            data=self.get_serializer(product).data,
            message="Product updated successfully.",
        )

    def put(self, request, product_pid: str, *args, **kwargs):
        return self.patch(request, product_pid, *args, **kwargs)


class VendorProductDeleteView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def delete(self, request, product_pid: str, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
            get_legacy_store_model("Product")
        except ValueError as exc:
            return error_response(
                message=str(exc),
                code="vendor_profile_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )
        except LegacyCommerceUnavailable:
            logger.warning("VendorProductDeleteView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response(
                "Vendor product deletion is temporarily unavailable while the product domain migration is completing."
            )

        try:
            product = profile.vendor_products.get(pid=product_pid)
        except ObjectDoesNotExist:
            return error_response(
                message="Product not found.",
                code="product_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )

        product.delete()
        return success_response(
            message="Product deleted successfully.",
            status=status.HTTP_200_OK,
        )


class VendorProductFilterView(generics.GenericAPIView):
    serializer_class = VendorProductListSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
            get_legacy_store_model("Product")
        except ValueError as exc:
            return error_response(
                message=str(exc),
                code="vendor_profile_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )
        except LegacyCommerceUnavailable:
            logger.warning("VendorProductFilterView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response(
                "Vendor product listings are temporarily unavailable while the product domain migration is completing."
            )

        status_filter = request.query_params.get("status", "").strip()
        ordering = request.query_params.get("ordering", "latest").strip()
        query = request.query_params.get("q", "").strip()

        products = profile.vendor_products.all()
        if query:
            products = products.filter(title__icontains=query)
        if status_filter in {"published", "draft", "disabled", "in-review"}:
            products = products.filter(status=status_filter)
        products = products.order_by("date" if ordering == "oldest" else "-date")

        serializer = self.get_serializer(products, many=True)
        return success_response(
            data=serializer.data,
            message="Vendor products retrieved successfully.",
        )


class VendorOrderStatusUpdateView(generics.GenericAPIView):
    serializer_class = VendorOrderStatusSerializer
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @transaction.atomic
    def patch(self, request, order_id: int, *args, **kwargs):
        try:
            profile = _get_profile_or_404(request.user)
            CartOrder = get_legacy_store_model("CartOrder")
        except ValueError as exc:
            return error_response(
                message=str(exc),
                code="vendor_profile_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )
        except LegacyCommerceUnavailable:
            logger.warning("VendorOrderStatusUpdateView unavailable: legacy store app is not installed")
            return _commerce_unavailable_response(
                "Vendor order status updates are temporarily unavailable while the order domain migration is completing."
            )

        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            order = profile.vendor_orders.get(pk=order_id)
        except ObjectDoesNotExist:
            try:
                order = CartOrder.objects.get(pk=order_id, vendor=profile)
            except ObjectDoesNotExist:
                return error_response(
                    message="Order not found.",
                    code="order_not_found",
                    status=status.HTTP_404_NOT_FOUND,
                )

        for attr, value in serializer.validated_data.items():
            setattr(order, attr, value)
        order.save(update_fields=list(serializer.validated_data.keys()))
        return success_response(
            data=serializer.data,
            message="Order status updated successfully.",
        )

    def put(self, request, order_id: int, *args, **kwargs):
        return self.patch(request, order_id, *args, **kwargs)
