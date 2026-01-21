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
from apps.authentication.throttles import BurstRateThrottle

logger = logging.getLogger('application')

class RegisterView(APIView):
    """
    Async View for User Registration.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request):
        try:
            # 1. Validate (Thread)
            serializer = AsyncUserRegistrationSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            validated_data = serializer.validated_data

            # 2. Service Call
            user, message = await AsyncRegistrationService.register_user(validated_data)
            
            return Response({
                "message": message,
                "user_id": user.id,
                "identifying_info": user.identifying_info
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Async Register Error: {e}")
            raise e


class LoginView(APIView):
    """
    Async View for Login.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request):
        try:
            # 1. Validate
            serializer = AsyncLoginSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            data = serializer.validated_data

            # 2. Authenticate
            tokens = await AsyncAuthService.login(
                data['email_or_phone'], 
                data['password'], 
                request
            )
            
            return Response({
                "message": "Login Successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Async Login Error: {e}")
            raise e


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request):
        otp_code = request.data.get('otp')
        user_id = request.data.get('user_id') 
        
        if not otp_code or not user_id:
            return Response({"error": "OTP and User ID required."}, status=status.HTTP_400_BAD_REQUEST)

        valid = await AsyncOTPService.verify_otp(user_id, otp_code)
        if valid:
            try:
                user = await UnifiedUser.objects.aget(pk=user_id)
                if not user.is_active:
                    user.is_active = True
                user.is_verified = True
                await user.asave()
                
                # Async Token Gen (Thread)
                from rest_framework_simplejwt.tokens import RefreshToken
                def _get_tokens():
                    refresh = RefreshToken.for_user(user)
                    return str(refresh.access_token), str(refresh)
                
                access, refresh = await asyncio.to_thread(_get_tokens)

                return Response({
                    "message": "Account Verified. Login Successful.",
                    'user_id': user.id,
                    'role': user.role,
                    'access': access,
                    'refresh': refresh,
                }, status=status.HTTP_200_OK)
            except UnifiedUser.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"error": "Invalid or Expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request):
        serializer = ResendOTPRequestSerializer(data=request.data)
        await asyncio.to_thread(serializer.is_valid, raise_exception=True)
        # Stub
        return Response({"message": "OTP Logic Pending"}, status=status.HTTP_200_OK)

class GoogleAuthView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        await asyncio.to_thread(serializer.is_valid, raise_exception=True)
        data = serializer.validated_data
        user = await AsyncGoogleAuthService.verify_and_login(data['id_token'], data.get('role', 'client'))
        
        from rest_framework_simplejwt.tokens import RefreshToken
        def _get_tokens():
             refresh = RefreshToken.for_user(user)
             return str(refresh.access_token), str(refresh)
        
        access, refresh = await asyncio.to_thread(_get_tokens)
        return Response({
            "message": "Google Login Successful",
             "tokens": {'access': access, 'refresh': refresh},
             "user": {"email": user.email, "role": user.role}
        })

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        return Response({"message": "Logout Successful"}, status=status.HTTP_200_OK)
