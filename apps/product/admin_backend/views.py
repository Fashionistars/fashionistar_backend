# apps/product/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.admin_backend.permissions import IsAdminUser
from apps.product.admin_backend.services import (
    admin_approve_product_sync,
    admin_reject_product_sync,
    admin_adjust_inventory_sync,
)
from apps.product.admin_backend.serializers import (
    AdminProductRejectSerializer,
    AdminInventoryAdjustSerializer,
)

logger = logging.getLogger(__name__)

class AdminProductApproveView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        try:
            product = admin_approve_product_sync(
                product_id=product_id,
                actor=request.user,
                request=request
            )
            return Response(
                {"status": "success", "message": f"Product {product.sku} approved successfully."},
                status=status.HTTP_200_OK
            )
        except Exception as exc:
            logger.exception("Product approval failed: %s", exc)
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )

class AdminProductRejectView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        serializer = AdminProductRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            product = admin_reject_product_sync(
                product_id=product_id,
                actor=request.user,
                reason=serializer.validated_data["reason"],
                request=request
            )
            return Response(
                {"status": "success", "message": f"Product {product.sku} rejected successfully."},
                status=status.HTTP_200_OK
            )
        except Exception as exc:
            logger.exception("Product rejection failed: %s", exc)
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )

class AdminInventoryAdjustView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        serializer = AdminInventoryAdjustSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            log = admin_adjust_inventory_sync(
                product_id=product_id,
                delta=serializer.validated_data["delta"],
                actor=request.user,
                reason=serializer.validated_data["reason"],
                note=serializer.validated_data.get("note", ""),
                request=request
            )
            return Response(
                {
                    "status": "success",
                    "message": "Inventory adjusted successfully.",
                    "data": {
                        "quantity_before": log.quantity_before,
                        "quantity_after": log.quantity_after,
                        "delta": log.quantity_delta
                    }
                },
                status=status.HTTP_200_OK
            )
        except Exception as exc:
            logger.exception("Inventory adjustment failed: %s", exc)
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )

