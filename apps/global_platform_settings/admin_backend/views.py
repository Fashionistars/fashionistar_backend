# apps/global_platform_settings/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.admin_backend.permissions import IsAdminUser
from .serializers import AdminPlatformSettingsUpdateSerializer
from .services import AdminSettingsService

logger = logging.getLogger(__name__)

class AdminPlatformSettingsUpdateView(APIView):
    """
    POST /api/admin/settings/update/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminPlatformSettingsUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            settings = AdminSettingsService.update_settings(
                data=serializer.validated_data,
                admin_user=request.user
            )
            return Response({
                "success": True,
                "message": "Global platform settings updated successfully.",
                "settings_id": str(settings.pk)
            })
        except Exception as exc:
            logger.exception("Failed to update global platform settings")
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

