# apps/kyc/admin_backend/views.py
"""DRF sync mutation views for KYC admin."""
from __future__ import annotations
import logging
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from apps.admin_backend.permissions import IsAdminUser
from .serializers import AdminKYCApproveSerializer, AdminKYCRejectSerializer
from .services import AdminKYCService

logger = logging.getLogger(__name__)


class AdminKYCApproveView(APIView):
    """POST /api/admin/kyc/{id}/approve/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, submission_id: str) -> Response:
        serializer = AdminKYCApproveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=400)
        try:
            submission = AdminKYCService.approve_kyc(
                submission_id=submission_id,
                legal_name=serializer.validated_data.get("legal_name", ""),
                admin_user=request.user,
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": "KYC submission approved.", "submission_id": str(submission.pk)})


class AdminKYCRejectView(APIView):
    """POST /api/admin/kyc/{id}/reject/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, submission_id: str) -> Response:
        serializer = AdminKYCRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=400)
        try:
            submission = AdminKYCService.reject_kyc(
                submission_id=submission_id,
                notes=serializer.validated_data["notes"],
                allow_resubmit=serializer.validated_data["allow_resubmit"],
                admin_user=request.user,
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": "KYC submission rejected.", "submission_id": str(submission.pk)})


class AdminKYCInReviewView(APIView):
    """POST /api/admin/kyc/{id}/in-review/"""
    permission_classes = [IsAdminUser]

    def post(self, request: Request, submission_id: str) -> Response:
        try:
            submission = AdminKYCService.mark_in_review(
                submission_id=submission_id, admin_user=request.user
            )
        except Exception as exc:
            return Response({"success": False, "message": str(exc)}, status=400)
        return Response({"success": True, "message": "KYC marked as under review.", "submission_id": str(submission.pk)})
