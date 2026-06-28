# apps/vendor/admin_backend/views.py
"""DRF sync mutation views for the vendor admin API."""

from __future__ import annotations
import logging
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_backend.permissions import IsAdminUser, IsSuperuserOnly
from .serializers import (
    AdminVendorSuspendSerializer,
    AdminVendorRejectSerializer,
    AdminVendorCommissionSerializer,
)
from .services import AdminVendorService

logger = logging.getLogger(__name__)


class AdminVendorApproveView(APIView):
    """POST /api/admin/vendor/{vendor_id}/approve/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, vendor_id: str) -> Response:
        try:
            vendor = AdminVendorService.approve_vendor(
                vendor_id=vendor_id, admin_user=request.user
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": f"Vendor {vendor.store_name} approved.", "vendor_id": str(vendor.pk)})


class AdminVendorSuspendView(APIView):
    """POST /api/admin/vendor/{vendor_id}/suspend/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, vendor_id: str) -> Response:
        serializer = AdminVendorSuspendSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=400)
        try:
            vendor = AdminVendorService.suspend_vendor(
                vendor_id=vendor_id,
                reason=serializer.validated_data["reason"],
                admin_user=request.user,
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": f"Vendor {vendor.store_name} suspended.", "vendor_id": str(vendor.pk)})


class AdminVendorReactivateView(APIView):
    """POST /api/admin/vendor/{vendor_id}/reactivate/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, vendor_id: str) -> Response:
        try:
            vendor = AdminVendorService.reactivate_vendor(
                vendor_id=vendor_id, admin_user=request.user
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": f"Vendor {vendor.store_name} reactivated.", "vendor_id": str(vendor.pk)})


class AdminVendorRejectView(APIView):
    """POST /api/admin/vendor/{vendor_id}/reject/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, vendor_id: str) -> Response:
        serializer = AdminVendorRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=400)
        try:
            vendor = AdminVendorService.reject_vendor(
                vendor_id=vendor_id,
                reason=serializer.validated_data["reason"],
                admin_user=request.user,
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": f"Vendor {vendor.store_name} rejected.", "vendor_id": str(vendor.pk)})


class AdminVendorCommissionView(APIView):
    """PATCH /api/admin/vendor/{vendor_id}/commission/"""
    permission_classes = [IsSuperuserOnly]

    def patch(self, request: Request, vendor_id: str) -> Response:
        serializer = AdminVendorCommissionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=400)
        try:
            AdminVendorService.update_vendor_commission(
                vendor_id=vendor_id,
                commission_rate=serializer.validated_data["commission_rate"],
                admin_user=request.user,
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": "Commission rate updated successfully."})


class AdminVendorFeaturedView(APIView):
    """PATCH /api/admin/vendor/{vendor_id}/featured/"""
    permission_classes = [IsAdminUser]

    def patch(self, request: Request, vendor_id: str) -> Response:
        featured = request.data.get("featured")
        if featured is None:
            return Response({"success": False, "errors": {"featured": "Required."}}, status=400)
        try:
            AdminVendorService.toggle_vendor_featured(
                vendor_id=vendor_id,
                featured=bool(featured),
                admin_user=request.user,
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": f"Vendor featured status set to {featured}."})
