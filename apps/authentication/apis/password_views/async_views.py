# apps/authentication/apis/password_views/async_views.py

import logging
import asyncio
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from adrf.views import APIView

from apps.common.renderers import CustomJSONRenderer
from apps.authentication.services.password_service import AsyncPasswordService
from apps.authentication.serializers import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordChangeSerializer
)

logger = logging.getLogger('application')

class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            serializer = PasswordResetRequestSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data
            
            message = await AsyncPasswordService.request_reset(validated_data['email_or_phone'])
            return Response({"message": message}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Reset Request Error (Async): {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmEmailView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request, uidb64, token):
        try:
            data = request.data.copy()
            data['uidb64'] = uidb64
            data['token'] = token
            
            serializer = PasswordResetConfirmEmailSerializer(data=data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data
            
            service_payload = {
                'uidb64': uidb64,
                'token': token,
                'new_password': validated_data['password']
            }
            
            msg = await AsyncPasswordService.confirm_reset(service_payload)
            return Response({"message": msg}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmPhoneView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            serializer = PasswordResetConfirmPhoneSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data
            
            service_payload = {
                'token': validated_data['otp'],
                'new_password': validated_data['password']
            }
            if 'phone' in request.data:
                service_payload['phone'] = request.data['phone']

            msg = await AsyncPasswordService.confirm_reset(service_payload)
            return Response({"message": msg}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data
            
            user = request.user
            user.set_password(validated_data['new_password'])
            await user.asave()
            return Response({"message": "Password changed successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
