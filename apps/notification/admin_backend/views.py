# apps/notification/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.admin_backend.permissions import IsAdminUser
from apps.notification.admin_backend.serializers import AdminBroadcastNotificationSerializer
from apps.notification.admin_backend.services import admin_broadcast_notification

logger = logging.getLogger(__name__)

class AdminBroadcastNotificationView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminBroadcastNotificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            count = admin_broadcast_notification(
                admin_user=request.user,
                notification_type=serializer.validated_data["notification_type"],
                title=serializer.validated_data["title"],
                body=serializer.validated_data["body"],
                target_role=serializer.validated_data.get("target_role"),
            )
            return Response({"status": "success", "message": f"Broadcasted notification to {count} users."}, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
