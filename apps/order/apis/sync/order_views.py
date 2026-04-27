# apps/order/apis/sync/order_views.py
"""
DRF Order views.

URL structure:
  Client:
    GET    /api/v1/orders/                → list user's orders
    POST   /api/v1/orders/place/          → place order from cart
    GET    /api/v1/orders/<id>/           → order detail
    POST   /api/v1/orders/<id>/cancel/    → client cancels
    POST   /api/v1/orders/<id>/confirm-delivery/ → release escrow

  Vendor:
    GET    /api/v1/orders/vendor/         → list vendor's orders
    GET    /api/v1/orders/vendor/<id>/    → vendor order detail
    POST   /api/v1/orders/vendor/<id>/transition/ → status update
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.renderers import success_response, error_response
from apps.common.permissions import IsAuthenticatedAndActive
from apps.order.serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    PlaceOrderSerializer,
    TransitionStatusSerializer,
)
from apps.order.services import (
    place_order,
    cancel_order,
    release_escrow,
    transition_status,
)
from apps.order.selectors import (
    get_user_orders,
    get_vendor_orders,
    get_order_by_id_for_user,
    get_order_by_id_for_vendor,
)
from apps.common.pagination import DefaultPagination

logger = logging.getLogger(__name__)

_PERMS = [IsAuthenticated, IsAuthenticatedAndActive]


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class ClientOrderListView(APIView):
    permission_classes = _PERMS

    def get(self, request):
        qs = get_user_orders(request.user.id)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        data = OrderListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class PlaceOrderView(APIView):
    permission_classes = _PERMS

    def post(self, request):
        serializer = PlaceOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            order = place_order(
                user=request.user,
                delivery_address=serializer.validated_data["delivery_address"],
                fulfillment_type=serializer.validated_data.get("fulfillment_type", "delivery"),
                idempotency_key=request.META.get("HTTP_X_IDEMPOTENCY_KEY"),
                measurement_profile_id=serializer.validated_data.get("measurement_profile_id"),
                notes=serializer.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=OrderDetailSerializer(order).data,
            message=f"Order #{order.order_number} placed successfully.",
            status=status.HTTP_201_CREATED,
        )


class ClientOrderDetailView(APIView):
    permission_classes = _PERMS

    def get(self, request, order_id):
        order = get_order_by_id_for_user(order_id, request.user.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data=OrderDetailSerializer(order).data)


class ClientCancelOrderView(APIView):
    permission_classes = _PERMS

    def post(self, request, order_id):
        order = get_order_by_id_for_user(order_id, request.user.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        try:
            order = cancel_order(
                order=order,
                actor=request.user,
                reason=request.data.get("reason", ""),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=OrderDetailSerializer(order).data,
            message=f"Order #{order.order_number} cancelled.",
        )


class ConfirmDeliveryView(APIView):
    """Client confirms delivery → releases escrow."""
    permission_classes = _PERMS

    def post(self, request, order_id):
        order = get_order_by_id_for_user(order_id, request.user.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        try:
            order = release_escrow(order=order, actor=request.user)
        except (ValueError, Exception) as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=OrderDetailSerializer(order).data,
            message=f"Order #{order.order_number} completed. Payment released to vendor.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class VendorOrderListView(APIView):
    permission_classes = _PERMS

    def _get_vendor(self, user):
        from apps.vendor.models import VendorProfile
        try:
            return VendorProfile.objects.get(user=user)
        except VendorProfile.DoesNotExist:
            return None

    def get(self, request):
        vendor = self._get_vendor(request.user)
        if not vendor:
            return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)
        status_filter = request.query_params.get("status")
        qs = get_vendor_orders(vendor.id, status=status_filter)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        data = OrderListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class VendorOrderDetailView(APIView):
    permission_classes = _PERMS

    def _get_vendor(self, user):
        from apps.vendor.models import VendorProfile
        try:
            return VendorProfile.objects.get(user=user)
        except VendorProfile.DoesNotExist:
            return None

    def get(self, request, order_id):
        vendor = self._get_vendor(request.user)
        if not vendor:
            return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)
        order = get_order_by_id_for_vendor(order_id, vendor.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data=OrderDetailSerializer(order).data)


class VendorOrderTransitionView(APIView):
    permission_classes = _PERMS

    def _get_vendor(self, user):
        from apps.vendor.models import VendorProfile
        try:
            return VendorProfile.objects.get(user=user)
        except VendorProfile.DoesNotExist:
            return None

    def post(self, request, order_id):
        vendor = self._get_vendor(request.user)
        if not vendor:
            return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)
        order = get_order_by_id_for_vendor(order_id, vendor.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        serializer = TransitionStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            order = transition_status(
                order=order,
                new_status=serializer.validated_data["new_status"],
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=OrderDetailSerializer(order).data,
            message=f"Order status updated to '{order.status}'.",
        )
