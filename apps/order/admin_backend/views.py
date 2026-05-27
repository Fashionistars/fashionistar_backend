# apps/order/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db import transaction

from apps.order.models.order import Order
from apps.order.admin_backend.serializers import (
    AdminOrderStatusTransitionSerializer,
    AdminOrderCancelSerializer,
)
from apps.order.admin_backend.services import (
    admin_transition_order_status,
    admin_release_escrow,
    admin_cancel_order,
)

logger = logging.getLogger(__name__)

class AdminOrderStatusTransitionView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(Order, pk=pk)
        serializer = AdminOrderStatusTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            with transaction.atomic():
                updated_order = admin_transition_order_status(
                    order=order,
                    new_status=serializer.validated_data["new_status"],
                    actor=request.user,
                    note=serializer.validated_data["note"],
                    request=request
                )
            return Response({
                "success": True,
                "message": f"Order status successfully updated to {updated_order.status}.",
                "order_id": str(updated_order.pk),
                "status": updated_order.status
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminOrderReleaseEscrowView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(Order, pk=pk)
        
        try:
            with transaction.atomic():
                updated_order = admin_release_escrow(
                    order=order,
                    actor=request.user,
                    request=request
                )
            return Response({
                "success": True,
                "message": "Escrow successfully released to vendor.",
                "order_id": str(updated_order.pk),
                "escrow_released": updated_order.escrow_released,
                "status": updated_order.status
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminOrderCancelView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(Order, pk=pk)
        serializer = AdminOrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            with transaction.atomic():
                updated_order = admin_cancel_order(
                    order=order,
                    actor=request.user,
                    reason=serializer.validated_data["reason"],
                    request=request
                )
            return Response({
                "success": True,
                "message": "Order successfully cancelled and stock returned.",
                "order_id": str(updated_order.pk),
                "status": updated_order.status
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
