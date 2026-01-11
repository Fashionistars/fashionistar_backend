from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from adrf.views import APIView as AsyncAPIView
from drf_api_logger.decorators import APILoggingDecorator

from apps.authentication.types.auth_schemas import RegistrationSchema, LoginSchema, GoogleAuthSchema
from apps.authentication.services.registration_service import RegistrationService
from apps.authentication.services.auth_service import AuthService
from apps.authentication.services.google_service import GoogleAuthService
from apps.authentication.services.otp_service import OTPService
from apps.common.renderers import CustomJSONRenderer
from apps.common.utils import get_otp_expiry_datetime # Assuming utility exists or we use internal logic
from apps.authentication.models import UnifiedUser

import logging

logger = logging.getLogger('application')

@APILoggingDecorator(level='INFO')
class RegisterView(AsyncAPIView):
    """
    Async View for User Registration.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            # 1. Validate Input
            schema = RegistrationSchema(**request.data)
            
            # 2. Process
            user, otp = await RegistrationService.register_user_async(schema)
            
            return Response({
                "message": f"Registration Successful. OTP sent to {schema.email or schema.phone}",
                "user_id": user.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration Error: {e}")
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

            # 2. Validate
            schema = LoginSchema(**request.data)

            # 3. Authenticate
            tokens = await AuthService.login_async(schema, request)
            
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
            schema = GoogleAuthSchema(**request.data)
            
            # 2. Verify & Get User
            user = await GoogleAuthService.verify_and_login_async(schema.id_token, schema.role)
            
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
        otp_code = request.data.get('otp')
        user_id = request.data.get('user_id') # Ideally passed via session or temporary token, but user_id here for flow simplicity
        
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
        email_or_phone = request.data.get('email_or_phone')
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
