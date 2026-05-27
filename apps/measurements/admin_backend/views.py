# apps/measurements/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.admin_backend.permissions import IsAdminUser
from apps.measurements.models.measurement import MeasurementProfile
from apps.measurements.admin_backend.serializers import AdminVerifyMeasurementSerializer
from apps.measurements.admin_backend.services import admin_verify_measurement_profile

logger = logging.getLogger(__name__)

class AdminVerifyMeasurementView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, profile_id):
        try:
            profile = MeasurementProfile.objects.get(id=profile_id)
        except MeasurementProfile.DoesNotExist:
            return Response({"status": "error", "message": "Measurement profile not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = AdminVerifyMeasurementSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            admin_verify_measurement_profile(
                profile_id=profile_id,
                admin_user=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
            return Response({"status": "success", "message": "Measurement profile verified successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
