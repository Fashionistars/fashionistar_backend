# apps/authentication/apis/auth_views/sync_views.py

import logging
from typing import Any, Dict
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from apps.authentication.serializers import (
    UserRegistrationSerializer, 
    LoginSerializer, 
    GoogleAuthSerializer,
    ResendOTPRequestSerializer,
    RefreshTokenSerializer # Assuming this exists or using simplejwt view
)
from apps.authentication.services.registration_service import SyncRegistrationService
from apps.authentication.services.auth_service import SyncAuthService
from apps.authentication.services.google_service import SyncGoogleAuthService
from apps.authentication.services.otp_service import SyncOTPService
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser
from apps.authentication.throttles import BurstRateThrottle, SustainedRateThrottle

logger = logging.getLogger('application')

class RegisterView(APIView):
    """
    Synchronous View for User Registration.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        try:
            # 1. Validate
            serializer = UserRegistrationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            validated_data: Dict[str, Any] = serializer.validated_data

            # 2. Service Call
            user, message = SyncRegistrationService.register_user(validated_data)
            
            return Response({
                "message": message,
                "user_id": user.id,
                "identifying_info": user.identifying_info
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"RegisterView Error: {e}")
            raise e

class LoginView(APIView):
    """
    Synchronous View for Login.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        try:
            # 1. Validate
            serializer = LoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data: Dict[str, Any] = serializer.validated_data

            # 2. Authenticate
            tokens = SyncAuthService.login(
                data['email_or_phone'], 
                data['password'], 
                request
            )
            
            return Response({
                "message": "Login Successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"LoginView Error: {e}")
            raise e

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        otp_code = request.data.get('otp')
        user_id = request.data.get('user_id')

        if not otp_code or not user_id:
             return Response({"error": "OTP and User ID required."}, status=status.HTTP_400_BAD_REQUEST)

        valid = SyncOTPService.verify_otp(user_id, otp_code, purpose="activation")
        if valid:
            try:
                user = UnifiedUser.objects.get(pk=user_id)
                if not user.is_active:
                    user.is_active = True
                user.is_verified = True
                user.save()
                
                from rest_framework_simplejwt.tokens import RefreshToken
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    "message": "Account Verified. Login Successful.",
                    'user_id': user.id,
                    'role': user.role,
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                }, status=status.HTTP_200_OK)
            except UnifiedUser.DoesNotExist:
                 return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
             return Response({"error": "Invalid or Expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        serializer = ResendOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Stub
        return Response({"message": "OTP Functionality Stub"}, status=status.HTTP_200_OK)

class GoogleAuthView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = SyncGoogleAuthService.verify_and_login(data['id_token'], data.get('role', 'client'))
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "Google Login Successful",
            "tokens": {'access': str(refresh.access_token), 'refresh': str(refresh)},
            "user": {"email": user.email, "role": user.role}
        })

class RefreshTokenView(APIView):
    """
    Manually wrapping SimpleJWT refresh if custom logic needed, else standard view is fine.
    Using standard view is better, but user asked for "RefreshTokenView" in URLs.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    
    def post(self, request) -> Response:
        from rest_framework_simplejwt.views import TokenRefreshView
        return TokenRefreshView.as_view()(request)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request) -> Response:
        # SimpleJWT is stateless, client deletes token. 
        # Optional: Blacklist token.
        return Response({"message": "Logout Successful"}, status=status.HTTP_200_OK)
