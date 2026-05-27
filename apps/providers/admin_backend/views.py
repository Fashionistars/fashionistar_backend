# apps/providers/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.admin_backend.permissions import IsAdminUser
from .serializers import (
    EmailProviderConfigUpdateSerializer,
    SMSProviderConfigUpdateSerializer,
    KYCProviderConfigUpdateSerializer,
    CloudinaryProviderConfigUpdateSerializer,
    MirrorSizeProviderConfigUpdateSerializer,
)
from .services import AdminProvidersService

logger = logging.getLogger(__name__)

class AdminEmailConfigUpdateView(APIView):
    """
    POST /api/admin/providers/email/update/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = EmailProviderConfigUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            config = AdminProvidersService.update_email_config(serializer.validated_data, request.user)
            return Response({"success": True, "message": "Email provider config updated successfully.", "id": str(config.pk)})
        except Exception as exc:
            logger.exception("Failed to update email provider config")
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminSMSConfigUpdateView(APIView):
    """
    POST /api/admin/providers/sms/update/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = SMSProviderConfigUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            config = AdminProvidersService.update_sms_config(serializer.validated_data, request.user)
            return Response({"success": True, "message": "SMS provider config updated successfully.", "id": str(config.pk)})
        except Exception as exc:
            logger.exception("Failed to update SMS provider config")
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminKYCConfigUpdateView(APIView):
    """
    POST /api/admin/providers/kyc/update/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = KYCProviderConfigUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            config = AdminProvidersService.update_kyc_config(serializer.validated_data, request.user)
            return Response({"success": True, "message": "KYC provider config updated successfully.", "id": str(config.pk)})
        except Exception as exc:
            logger.exception("Failed to update KYC provider config")
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminCloudinaryConfigUpdateView(APIView):
    """
    POST /api/admin/providers/cloudinary/update/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = CloudinaryProviderConfigUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            config = AdminProvidersService.update_cloudinary_config(serializer.validated_data, request.user)
            return Response({"success": True, "message": "Cloudinary provider config updated successfully.", "id": str(config.pk)})
        except Exception as exc:
            logger.exception("Failed to update Cloudinary provider config")
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminMirrorSizeConfigUpdateView(APIView):
    """
    POST /api/admin/providers/mirrorsize/update/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = MirrorSizeProviderConfigUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            config = AdminProvidersService.update_mirrorsize_config(serializer.validated_data, request.user)
            return Response({"success": True, "message": "MirrorSize provider config updated successfully.", "id": str(config.pk)})
        except Exception as exc:
            logger.exception("Failed to update MirrorSize provider config")
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
