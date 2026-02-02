# apps/authentication/apis/auth_views/async_views.py

import logging
import asyncio
from typing import Any, Dict
from ninja import Router
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from adrf.views import APIView

from apps.authentication.types.auth_schemas import (
    RegistrationSchema, 
    VerifyOTPSchema, 
    ResendOTPSchema
)
from apps.authentication.services.registration_service import RegistrationService
from apps.authentication.services.otp_service import OTPService
from apps.authentication.serializers import (
    AsyncUserRegistrationSerializer,
    AsyncLoginSerializer,
    GoogleAuthSerializer,
    ResendOTPRequestSerializer
)
# from apps.authentication.services.registration_service_legacy import AsyncRegistrationService as LegacyAsyncRegistrationService
from apps.authentication.services.auth_service import AsyncAuthService
from apps.authentication.services.google_service import AsyncGoogleAuthService
from apps.authentication.services.otp_service import AsyncOTPService
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser
from apps.authentication.throttles import BurstRateThrottle

logger = logging.getLogger('application')

# =============================================================================
# DJANGO NINJA ROUTER (V2 API)
# =============================================================================

auth_router = Router()

@auth_router.post("/register", response={201: Dict[str, Any]}, auth=None)
async def register(request, data: RegistrationSchema):
    """
    Async User Registration (Django Ninja).
    Handles User Creation, OTP Generation, and Notification Dispatch.
    """
    try:
        # Pydantic schema 'data' is already validated
        validated_data = data.dict()
        
        # Call Service
        result = await RegistrationService.register_async(
            request=request, 
            **validated_data
        )
        
        return 201, result

    except Exception as e:
        logger.error(f"Async Register Error: {e}")
        # Ninja handles exceptions if we have specific handlers, or 500
        # We can re-raise specific HttpErrors if needed
        raise e

@auth_router.post("/verify-otp", response={200: Dict[str, Any]}, auth=None)
async def verify_otp(request, data: VerifyOTPSchema):
    """
    Async OTP Verification (Django Ninja).
    Verifies OTP, activates account, and returns JWT tokens.
    """
    try:
        # Verify
        valid = await OTPService.verify_otp_async(user_id=data.user_id, otp=data.otp)
        
        if valid:
            # Activate and Get Tokens
            # Ideally this logic moves to OTPService or AuthService to keep View thin
            # But per roadmap, we can verify and then act.
            # Let's clean this up by moving token generation to Service if possible,
            # but for now, we follow the pattern established in the service or sync view.
            
            # Using OTPService directly doesn't yield tokens, need to construct response.
            user = await UnifiedUser.objects.aget(pk=data.user_id)
            if not user.is_active:
                user.is_active = True
            user.is_verified = True
            await user.asave()
            
            from rest_framework_simplejwt.tokens import RefreshToken
            def _get_tokens():
                refresh = RefreshToken.for_user(user)
                return str(refresh.access_token), str(refresh)
            
            access, refresh = await asyncio.to_thread(_get_tokens)

            return 200, {
                "message": "Account Verified. Login Successful.",
                'user_id': user.id,
                'role': user.role,
                'access': access,
                'refresh': refresh,
            }
        else:
            # Ninja expects HTTP exceptions or specific return codes
            # Returning 400 manually or raising exception
            # We can use ninja.errors.HttpError(400, "...")
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid or Expired OTP.")

    except UnifiedUser.DoesNotExist:
        from ninja.errors import HttpError
        raise HttpError(404, "User not found.")
    except Exception as e:
        logger.error(f"Async Verify OTP Error: {e}")
        raise e

@auth_router.post("/resend-otp", response={200: Dict[str, Any]}, auth=None)
async def resend_otp(request, data: ResendOTPSchema):
    """
    Async Resend OTP (Django Ninja).
    Invalidates old OTP and sends a new one via Email/SMS.
    """
    try:
        message = await OTPService.resend_otp_async(email_or_phone=data.email_or_phone)
        return 200, {"message": message}
    except Exception as e:
        logger.error(f"Async Resend OTP Error: {e}")
        # Return generic error to user or re-raise
        from ninja.errors import HttpError
        raise HttpError(500, "Failed to resend OTP.")

# =============================================================================
# ADRF VIEWS (Legacy/Transition Compatibility)
# =============================================================================

# Deprecated AsyncRegisterView removed.
# Deprecated VerifyOTPView (ADRF) removed/commented out since Ninja covers it 
# BUT explicit URLs might still point to adrf views.
# We should keep ADRF views if they are separately routed in urls.py until fully switched.
# However, the roadmap implies we implement the Async endpoints. Ninja is the preferred way.

class AsyncLoginView(APIView):
    """
    Async View for Login.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request) -> Response:
        try:
            # 1. Validate
            serializer = AsyncLoginSerializer(data=request.data)
            await asyncio.to_thread(serializer.is_valid, raise_exception=True)
            data: Dict[str, Any] = serializer.validated_data

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

class AsyncLogoutView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request) -> Response:
        return Response({"message": "Logout Successful"}, status=status.HTTP_200_OK)

class AsyncRefreshTokenView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request) -> Response:
        # ADRF wrapper for SimpleJWT refresh view 
        from rest_framework_simplejwt.views import TokenRefreshView
        try:
            # Need to instantiate properly or use logic
            view = TokenRefreshView.as_view()
            # This is likely blocking without wrapper, but acceptable for now
            response = await asyncio.to_thread(view, request)
            return response
        except Exception as e:
             logger.error(f"Refresh Token Error: {e}")
             raise e

# Kept for backward compatibility if `urls.py` still points here, otherwise Ninja route takes precedence if configured
class VerifyOTPView(APIView):
    # Should rename to AsyncVerifyOTPView in future refactor to match convention but user URLs might need check
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    async def post(self, request) -> Response:
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
