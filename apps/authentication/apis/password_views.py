from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from adrf.views import APIView as AsyncAPIView
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.services.password_service import PasswordService
from apps.authentication.types.auth_schemas import PasswordResetRequestSchema, PasswordResetConfirmSchema, ChangePasswordSchema
import logging

logger = logging.getLogger('application')

class PasswordResetRequestView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            schema = PasswordResetRequestSchema(**request.data)
            message = await PasswordService.request_reset_async(schema.email_or_phone)
            return Response({"message": message}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Reset Request Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmEmailView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request, uidb64, token):
        try:
            data = request.data.copy()
            data['uidb64'] = uidb64
            data['token'] = token
            
            schema = PasswordResetConfirmSchema(**data)
            msg = await PasswordService.confirm_reset_async(schema.dict())
            return Response({"message": msg}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Reset Confirm Email Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmPhoneView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            schema = PasswordResetConfirmSchema(**request.data)
            msg = await PasswordService.confirm_reset_async(schema.dict())
            return Response({"message": msg}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Reset Confirm Phone Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            schema = ChangePasswordSchema(**request.data)
            user = request.user
            if not user.check_password(schema.old_password):
                return Response({"error": "Incorrect old password."}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(schema.new_password)
            await user.asave()
            return Response({"message": "Password changed successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
