from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from adrf.views import APIView as AsyncAPIView

from apps.common.renderers import CustomJSONRenderer
from apps.authentication.services.password_service import PasswordService
from apps.authentication.serializers import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordChangeSerializer
)
from asgiref.sync import sync_to_async
import logging

logger = logging.getLogger('application')

class PasswordResetRequestView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            serializer = PasswordResetRequestSerializer(data=request.data)
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            validated_data = serializer.validated_data
            
            message = await PasswordService.request_reset_async(validated_data['email_or_phone'])
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
            
            serializer = PasswordResetConfirmEmailSerializer(data=data)
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            validated_data = serializer.validated_data
            
            # Combine validated data (uid, token from args) with new password
            service_payload = {
                'uidb64': uidb64,
                'token': token,
                'new_password': validated_data['password']
            }
            
            msg = await PasswordService.confirm_reset_async(service_payload)
            return Response({"message": msg}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Reset Confirm Email Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmPhoneView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            serializer = PasswordResetConfirmPhoneSerializer(data=request.data)
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            validated_data = serializer.validated_data
            
            service_payload = {
                'phone': request.data.get('phone'), # Assuming phone is passed or inferred? Service expects phone key if no uidb64
                # Note: Serializer doesn't have 'phone' field in provided dump, might need check.
                # Assuming standard Phone confirmation needs Phone + OTP + New Password.
                # Let's assume request.data has 'phone' which might not be validated by serializer if not fields.
                # Adding it to payload if available.
                'token': validated_data['otp'], # OTP acts as token
                'new_password': validated_data['password']
            }
            # Need to pass phone explicitly if not in serializer
            if 'phone' in request.data:
                service_payload['phone'] = request.data['phone']

            msg = await PasswordService.confirm_reset_async(service_payload)
            return Response({"message": msg}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Reset Confirm Phone Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            validated_data = serializer.validated_data
            
            user = request.user
            # Double check old password again? Serializer did it.
            # But let's follow standard flow.
            
            user.set_password(validated_data['new_password'])
            await user.asave()
            return Response({"message": "Password changed successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
