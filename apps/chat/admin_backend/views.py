# apps/chat/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.admin_backend.permissions import IsAdminUser
from apps.chat.models.conversation import ChatEscalation
from .serializers import AdminResolveEscalationSerializer
from .services import admin_resolve_escalation

logger = logging.getLogger(__name__)

class AdminResolveEscalationView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, escalation_id):
        try:
            escalation = ChatEscalation.objects.get(id=escalation_id)
        except ChatEscalation.DoesNotExist:
            return Response({"status": "error", "message": "Escalation case not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = AdminResolveEscalationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            resolved = admin_resolve_escalation(
                escalation_id=escalation_id,
                admin_user=request.user,
                notes=serializer.validated_data["notes"],
                resolution_status=serializer.validated_data["resolution_status"],
            )
            return Response(
                {
                    "status": "success",
                    "id": str(resolved.id),
                    "escalation_status": resolved.status,
                },
                status=status.HTTP_200_OK
            )
        except Exception as exc:
            logger.exception("Error resolving chat escalation")
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
