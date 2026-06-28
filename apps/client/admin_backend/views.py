# apps/client/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.common.renderers import CustomJSONRenderer, success_response
from apps.client.admin_backend.services import AdminClientService
from apps.client.admin_backend.serializers import AdminClientProfileUpdateSerializer

logger = logging.getLogger(__name__)

class AdminClientProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def put(self, request, profile_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        serializer = AdminClientProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            profile = AdminClientService.update_client_profile(
                profile_id=profile_id,
                data=serializer.validated_data,
                admin_user=request.user
            )
            return success_response(
                data={"profile_id": str(profile.id)},
                message="Client profile updated successfully."
            )
        except Exception as e:
            logger.error("Error updating client profile %s: %s", profile_id, e)
            raise ValidationError(str(e))
            
    def patch(self, request, profile_id, *args, **kwargs):
        return self.put(request, profile_id, *args, **kwargs)
