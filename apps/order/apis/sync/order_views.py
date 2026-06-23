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
from apps.common.permissions import IsClient
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
    update_delivery_status,
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
_CLIENT_PERMS = [IsAuthenticated, IsAuthenticatedAndActive, IsClient]


def _get_vendor_profile_from_user(user):
    """Return the vendor profile through request.user reverse relationships.

    Traversal:
        request.user.vendor_profile -> VendorProfile
        request.user.vendorprofile  -> legacy compatibility alias

    API views must not import and query ``VendorProfile.objects`` directly.
    Starting from the authenticated user makes ownership explicit and keeps
    future vendor/order joins aligned with the Wave 4 reverse-relation rule.
    """
    return getattr(user, "vendor_profile", None) or getattr(user, "vendorprofile", None)


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class ClientOrderListView(APIView):
    permission_classes = _CLIENT_PERMS

    def get(self, request):
        qs = get_user_orders(request.user.id)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        data = OrderListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class PlaceOrderView(APIView):
    permission_classes = _CLIENT_PERMS

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
                items=serializer.validated_data["items"],
                coupon_code=serializer.validated_data.get("coupon_code"),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=OrderDetailSerializer(order).data,
            message=f"Order #{order.order_number} placed successfully.",
            status=status.HTTP_201_CREATED,
        )


class ClientOrderDetailView(APIView):
    permission_classes = _CLIENT_PERMS

    def get(self, request, order_id):
        order = get_order_by_id_for_user(order_id, request.user.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data=OrderDetailSerializer(order).data)


class ClientCancelOrderView(APIView):
    permission_classes = _CLIENT_PERMS

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
    permission_classes = _CLIENT_PERMS

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

    def get(self, request):
        vendor = _get_vendor_profile_from_user(request.user)
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

    def get(self, request, order_id):
        vendor = _get_vendor_profile_from_user(request.user)
        if not vendor:
            return error_response(message="Vendor profile not found.", status=status.HTTP_403_FORBIDDEN)
        order = get_order_by_id_for_vendor(order_id, vendor.id)
        if not order:
            return error_response(message="Order not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data=OrderDetailSerializer(order).data)


class VendorOrderTransitionView(APIView):
    permission_classes = _PERMS

    def post(self, request, order_id):
        vendor = _get_vendor_profile_from_user(request.user)
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

    def patch(self, request, order_id):
        """PATCH alias used by the frontend production-status mutation."""
        return self.post(request, order_id)


class AdminDeliveryStatusView(APIView):
    """Admin/staff delivery-status update endpoint.

    This is a DRF sync mutation because it changes order state and may trigger
    later escrow/provider reconciliation. The service performs the row lock;
    the view only validates input, checks high-trust staff access, and returns
    the serialized order.
    """

    permission_classes = _PERMS

    def patch(self, request, order_id):
        if not (request.user.is_staff or request.user.is_superuser):
            return error_response(message="Admin access required.", status=status.HTTP_403_FORBIDDEN)
        serializer = TransitionStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        try:
            order = update_delivery_status(
                order_id=order_id,
                new_status=serializer.validated_data["new_status"],
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
                tracking_number=request.data.get("tracking_number", ""),
            )
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=OrderDetailSerializer(order).data,
            message=f"Order delivery status updated to '{order.status}'.",
        )


class VerifyPickupView(APIView):
    """Verify order pickup token, release escrow, and transition to Completed status."""
    permission_classes = _PERMS

    def put(self, request):
        token = request.data.get("pickup_token", "")
        if not token:
            return error_response(message="pickup_token is required.", status=status.HTTP_400_BAD_REQUEST)

        parts = token.split("-")
        order_id = parts[-1] if len(parts) > 1 else token

        from apps.order.models import Order
        try:
            order = Order.objects.get(id=order_id)
        except (Order.DoesNotExist, ValueError):
            return error_response(message="Invalid pickup token or Order not found.", status=status.HTTP_404_NOT_FOUND)

        try:
            order = release_escrow(order=order, actor=request.user)
            if order.status != "completed":
                order = transition_status(
                    order=order,
                    new_status="completed",
                    actor=request.user,
                    note="Verified via shop QR pickup scan."
                )
        except (ValueError, Exception) as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=OrderDetailSerializer(order).data,
            message="Order Pickup Verified",
        )

