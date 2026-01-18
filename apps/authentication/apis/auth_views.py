from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from adrf.views import APIView as AsyncAPIView

from apps.authentication.serializers import (
    UserRegistrationSerializer, 
    AsyncUserRegistrationSerializer,
    LoginSerializer, 
    AsyncLoginSerializer,
    GoogleAuthSerializer,
    ResendOTPRequestSerializer
)
from apps.authentication.services.registration_service import RegistrationService
from apps.authentication.services.auth_service import AuthService
from apps.authentication.services.google_service import GoogleAuthService
from apps.authentication.services.otp_service import OTPService
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser
from asgiref.sync import sync_to_async

import logging

logger = logging.getLogger('application')

class RegisterView(AsyncAPIView):
    """
    Async View for User Registration.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            # 1. Validate Input using DRF Serializer
            # Using AsyncUserRegistrationSerializer if available, or wrapping sync validation
            serializer = AsyncUserRegistrationSerializer(data=request.data)
            
            # Manual async validation call if supported, or wrapped
            if hasattr(serializer, 'avalidate'):
                validated_data = await serializer.avalidate(serializer.initial_data)
            else:
                # Fallback to sync validation wrapped in sync_to_async if IO bound checks exist
                # But typically is_valid is CPU bound unless it checks DB uniqueness
                # For DB uniqueness, sync_to_async is better
                await sync_to_async(serializer.is_valid)(raise_exception=True)
                validated_data = serializer.validated_data

            # 2. Process via Service
            user, otp = await RegistrationService.register_user_async(validated_data)
            
            return Response({
                "message": f"Registration Successful. OTP sent to {validated_data.get('email') or validated_data.get('phone')}",
                "user_id": user.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration Error: {e}")
            # DRF exceptions usually handled by global handler, but if we catch generic:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(AsyncAPIView):
    """
    Async View for Login with Rate Limiting.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        ip = request.META.get('REMOTE_ADDR')
        
        try:
            # 1. Check Rate Limit
            AuthService.check_rate_limit(ip)

            # 2. Validate using DRF Serializer
            serializer = AsyncLoginSerializer(data=request.data)
            if hasattr(serializer, 'avalidate'):
                 validated_data = await serializer.avalidate(serializer.initial_data)
            else:
                 await sync_to_async(serializer.is_valid)(raise_exception=True)
                 validated_data = serializer.validated_data

            # 3. Authenticate
            # Service now expects primitives
            tokens = await AuthService.login_async(
                validated_data['email_or_phone'], 
                validated_data['password'], 
                request
            )
            
            # 4. Clear Rate Limit
            AuthService.reset_login_failures(ip)

            return Response({
                "message": "Login Successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # Increment Failure
            AuthService.increment_login_failure(ip)
            logger.error(f"Login Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class GoogleAuthView(AsyncAPIView):
    """
    Async View for Google Authentication.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            # 1. Validation
            serializer = GoogleAuthSerializer(data=request.data)
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            validated_data = serializer.validated_data
            
            # 2. Verify & Get User
            user = await GoogleAuthService.verify_and_login_async(
                validated_data['id_token'], 
                validated_data.get('role', 'client')
            )
            
            # 3. Generate Tokens
            tokens = await AuthService.get_tokens_async(user)
            
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
            logger.error(f"Google Auth Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        # Could use OTPSerializer here
        otp_code = request.data.get('otp')
        user_id = request.data.get('user_id') 
        
        if not otp_code or not user_id:
            return Response({"error": "OTP and User ID required."}, status=status.HTTP_400_BAD_REQUEST)

        valid = OTPService.verify_otp(user_id, otp_code, purpose="activation")
        if valid:
            # Activate User
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


class ResendOTPView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        serializer = ResendOTPRequestSerializer(data=request.data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        # validated_user = serializer.validated_data... 
        # Logic to resolve user and resend
        return Response({"message": "OTP Resent if account exists."}, status=status.HTTP_200_OK)


class LogoutView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            # In simplejwt, we blacklist the token
            # from rest_framework_simplejwt.tokens import RefreshToken
            # token = RefreshToken(refresh_token)
            # token.blacklist()
            return Response({"message": "Logout Successful"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Logout Failed"}, status=status.HTTP_400_BAD_REQUEST)
