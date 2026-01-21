# apps/authentication/apis/biometric_views/sync_views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.services.biometric_service import SyncBiometricService
from apps.authentication.models import UnifiedUser
import logging

logger = logging.getLogger('application')

class BiometricRegisterOptionsView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request):
        try:
            options, state = SyncBiometricService.generate_registration_options(request.user)
            request.session["biometric_reg_state"] = state
            return Response(dict(options), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricRegisterVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request):
        try:
            state = request.session.get("biometric_reg_state")
            if not state:
                return Response({"error": "State missing. Restart registration."}, status=status.HTTP_400_BAD_REQUEST)

            SyncBiometricService.verify_registration_response(
                request.user,
                request.data,
                state,
                device_name=request.data.get("device_name", "Unknown Device")
            )
            return Response({"message": "Biometric registration successful."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricLoginOptionsView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request):
        try:
            email = request.data.get('email')
            if not email:
                return Response({"error": "Email required."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user = UnifiedUser.objects.get(email=email)
            except UnifiedUser.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
            options, state = SyncBiometricService.generate_auth_options(user)
            request.session["biometric_auth_state"] = state
            request.session["biometric_auth_user"] = user.id
            
            return Response(dict(options), status=status.HTTP_200_OK)
        except Exception as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BiometricLoginVerifyView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request):
        try:
            state = request.session.get("biometric_auth_state")
            user_id = request.session.get("biometric_auth_user")
            
            if not state or not user_id:
                return Response({"error": "Session expired."}, status=status.HTTP_400_BAD_REQUEST)

            user = UnifiedUser.objects.get(pk=user_id)
            
            SyncBiometricService.verify_auth_response(user, request.data, state)
            
            # Login successful, generate tokens
            from apps.authentication.services.auth_service import SyncAuthService
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)
            tokens = {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
            
            return Response({"message": "Login Successful", "tokens": tokens}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
