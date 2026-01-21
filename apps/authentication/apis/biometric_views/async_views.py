# apps/authentication/apis/biometric_views/async_views.py

import logging
import asyncio
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from adrf.views import APIView
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.services.biometric_service import AsyncBiometricService
from apps.authentication.models import UnifiedUser

logger = logging.getLogger('application')

class BiometricRegisterOptionsView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            options, state = await AsyncBiometricService.generate_registration_options(request.user)
            
            # Helper to set session async (SessionMiddleware is sync usually, wrap it)
            # Or use request.session directly if async adapter exists, but safe bet:
            await asyncio.to_thread(request.session.__setitem__, "biometric_reg_state", state)
            
            return Response(dict(options), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricRegisterVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            state = await asyncio.to_thread(request.session.get, "biometric_reg_state")
            if not state:
                return Response({"error": "State missing. Restart registration."}, status=status.HTTP_400_BAD_REQUEST)

            await AsyncBiometricService.verify_registration_response(
                request.user,
                request.data,
                state,
                device_name=request.data.get("device_name", "Unknown Device")
            )
            return Response({"message": "Biometric registration successful."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Biometric Reg Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricLoginOptionsView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            email = request.data.get('email')
            if not email:
                return Response({"error": "Email required."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user = await UnifiedUser.objects.aget(email=email)
            except UnifiedUser.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
            options, state = await AsyncBiometricService.generate_auth_options(user)
            
            await asyncio.to_thread(request.session.__setitem__, "biometric_auth_state", state)
            await asyncio.to_thread(request.session.__setitem__, "biometric_auth_user", user.id)
            
            return Response(dict(options), status=status.HTTP_200_OK)
        except Exception as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricLoginVerifyView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            state = await asyncio.to_thread(request.session.get, "biometric_auth_state")
            user_id = await asyncio.to_thread(request.session.get, "biometric_auth_user")
            
            if not state or not user_id:
                return Response({"error": "Session expired."}, status=status.HTTP_400_BAD_REQUEST)

            user = await UnifiedUser.objects.aget(pk=user_id)
            
            await AsyncBiometricService.verify_auth_response(user, request.data, state)
            
            from apps.authentication.services.auth_service import AsyncAuthService
            tokens = await AsyncAuthService.get_tokens(user)
            
            return Response({"message": "Login Successful", "tokens": tokens}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Biometric Login Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
