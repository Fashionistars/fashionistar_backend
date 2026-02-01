# apps/authentication/apis/auth_views/async_views.py

import logging
import asyncio
from typing import Any, Dict
from ninja import Router
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from adrf.views import APIView

from apps.authentication.types.auth_schemas import RegistrationSchema
from apps.authentication.services.registration_service import RegistrationService
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


# =============================================================================
# ADRF VIEWS (Legacy/Transition)
# =============================================================================

# class AsyncRegisterView(APIView):
#     """
#     Async View for User Registration.
#     DEPRECATED: Use Ninja Router 'auth_router' instead.
#     """
#     permission_classes = [AllowAny]
#     renderer_classes = [CustomJSONRenderer]
#     throttle_classes = [BurstRateThrottle]
#
#     async def post(self, request) -> Response:
#         try:
#             # 1. Validate
#             serializer = AsyncUserRegistrationSerializer(data=request.data)
#             await asyncio.to_thread(serializer.is_valid, raise_exception=True)
#             validated_data: Dict[str, Any] = serializer.validated_data
#
#             # 2. Service Call
#             user, message = await LegacyAsyncRegistrationService.register_user(validated_data)
#             
#             return Response({
#                 "message": message,
#                 "user_id": user.id,
#                 "identifying_info": user.identifying_info
#             }, status=status.HTTP_201_CREATED)
# 
#         except Exception as e:
#             logger.error(f"Async Register Error: {e}")
#             raise e

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
