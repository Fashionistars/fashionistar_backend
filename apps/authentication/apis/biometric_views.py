from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from adrf.views import APIView as AsyncAPIView
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.services.biometric_service import BiometricService
from apps.authentication.models import UnifiedUser
from asgiref.sync import sync_to_async
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import logging
import base64
import json

logger = logging.getLogger('application')

class BiometricRegisterOptionsView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            options, state = await BiometricService.generate_registration_options_async(request.user)
            # Store state in session (Sync op in async view, need wrapper if session backend is DB-based, but usually strict async views avoid session).
            # For simplicity in this hybrid setup, we assume we can set session. 
            # In pure async DRF with async session storage it's clean, otherwise wrap.
            await sync_to_async(request.session.__setitem__)("biometric_reg_state", state)
            
            # Serialize options for JSON (bytes to base64 or internal dict)
            # fido2 library returns a dict-like object, we need to ensure bytes are converted if any
            # The library helper `dict(options)` might not be enough for JSONRenderer if it contains bytes
            return Response(dict(options), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricRegisterVerifyView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            state = await sync_to_async(request.session.get)("biometric_reg_state")
            if not state:
                return Response({"error": "State missing. Restart registration."}, status=status.HTTP_400_BAD_REQUEST)

            success = await BiometricService.verify_registration_response_async(
                request.user, 
                request.data, 
                state,
                device_name=request.data.get("device_name", "Unknown Device")
            )
            return Response({"message": "Biometric registration successful."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Biometric Reg Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricLoginOptionsView(AsyncAPIView):
    permission_classes = [AllowAny] # Or partially authenticated (username known)
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
            
            options, state = await BiometricService.generate_auth_options_async(user)
            await sync_to_async(request.session.__setitem__)("biometric_auth_state", state)
            await sync_to_async(request.session.__setitem__)("biometric_auth_user", user.id)
            
            return Response(dict(options), status=status.HTTP_200_OK)
        except Exception as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricLoginVerifyView(AsyncAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    async def post(self, request):
        try:
            state = await sync_to_async(request.session.get)("biometric_auth_state")
            user_id = await sync_to_async(request.session.get)("biometric_auth_user")
            
            if not state or not user_id:
                return Response({"error": "Session expired."}, status=status.HTTP_400_BAD_REQUEST)

            user = await UnifiedUser.objects.aget(pk=user_id)
            
            success = await BiometricService.verify_auth_response_async(
                user,
                request.data,
                state
            )
            
            # Login successful, generate tokens
            from apps.authentication.services.auth_service import AuthService
            tokens = await AuthService.get_tokens_async(user)
            
            return Response({"message": "Login Successful", "tokens": tokens}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Biometric Login Error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
