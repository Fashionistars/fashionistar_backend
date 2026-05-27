# apps/custom_order/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from apps.common.permissions import IsAdminUser  # Or whichever admin permission class is standard in the repo
from .serializers import AdminCustomOrderStatusUpdateSerializer
from .services import admin_update_custom_order_status

logger = logging.getLogger(__name__)

class AdminCustomOrderStatusUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, custom_order_id):
        serializer = AdminCustomOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        status_val = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")
        
        try:
            order = admin_update_custom_order_status(
                custom_order_id=custom_order_id,
                status=status_val,
                admin_user=request.user,
                reason=reason,
            )
            return Response(
                {
                    "success": True,
                    "id": str(order.id),
                    "status": order.status,
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.exception("Error updating custom order status")
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
