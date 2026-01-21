# apps/authentication/apis/auth_views/async_views.py

import logging
import asyncio
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from adrf.views import APIView

from apps.authentication.serializers import (
    AsyncUserRegistrationSerializer,
    AsyncLoginSerializer,
    GoogleAuthSerializer,
    ResendOTPRequestSerializer
)
from apps.authentication.services.registration_service import AsyncRegistrationService
from apps.authentication.services.auth_service import AsyncAuthService
from apps.authentication.services.google_service import AsyncGoogleAuthService
from apps.authentication.services.otp_service import AsyncOTPService
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser

logger = logging.getLogger('application')

class RegisterView(APIView):
    """
    Async View for User Registration.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            # 1. Validate (Offload Sync Serializer to Thread)
            serializer = AsyncUserRegistrationSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data

            # 2. Service Call
            user, otp = await AsyncRegistrationService.register_user(validated_data)
            
            return Response({
                "message": f"Registration Successful. OTP sent to {validated_data.get('email') or validated_data.get('phone')}",
                "user_id": user.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration Error (Async): {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    Async View for Login.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        ip = request.META.get('REMOTE_ADDR')
        try:
            # 1. Rate Limit
            await AsyncAuthService.check_rate_limit(ip)

            # 2. Validate
            serializer = AsyncLoginSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            data = serializer.validated_data

            # 3. Authenticate
            tokens = await AsyncAuthService.login(
                data['email_or_phone'], 
                data['password'], 
                request
            )
            
            # 4. Clear Limit
            await AsyncAuthService.reset_login_failures(ip)

            return Response({
                "message": "Login Successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)

        except Exception as e:
            await AsyncAuthService.increment_login_failure(ip)
            logger.error(f"Login Error (Async): {e}")
            return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class GoogleAuthView(APIView):
    """
    Async View for Google Authentication.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            # 1. Validation
            serializer = GoogleAuthSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data
            
            # 2. Verify & Get User
            user = await AsyncGoogleAuthService.verify_and_login(
                validated_data['id_token'], 
                validated_data.get('role', 'client')
            )
            
            # 3. Generate Tokens
            tokens = await AsyncAuthService.get_tokens(user)
            
            return Response({
                "message": "Google Authentication Successful",
                "tokens": tokens,
                "user": {
                    "email": user.email,
                    "role": user.role,
                    "auth_provider": user.auth_provider
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Google Auth Error (Async): {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        otp_code = request.data.get('otp')
        user_id = request.data.get('user_id') 
        
        if not otp_code or not user_id:
            return Response({"error": "OTP and User ID required."}, status=status.HTTP_400_BAD_REQUEST)

        valid = await AsyncOTPService.verify_otp(user_id, otp_code, purpose="activation")
        if valid:
            try:
                user = await UnifiedUser.objects.aget(pk=user_id)
                user.is_active = True
                user.is_verified = True
                await user.asave()
                return Response({"message": "Account Verified Successfully."}, status=status.HTTP_200_OK)
            except UnifiedUser.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"error": "Invalid or Expired OTP."}, status=status.HTTP_400_BAD_REQUEST)


class ResendOTPView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        serializer = ResendOTPRequestSerializer(data=request.data)
        await asyncio.to_thread(serializer.is_valid, raise_exception=True)
        return Response({"message": "OTP Resent if account exists."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            return Response({"message": "Logout Successful"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Logout Failed"}, status=status.HTTP_400_BAD_REQUEST)
