# apps/authentication/apis/biometric_views/sync_views.py
"""
Biometric Authentication Views — Sync DRF
=========================================

Endpoints for Passkey (WebAuthn) registration and login.
"""

import logging
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.renderers import CustomJSONRenderer, error_response, success_response
from apps.authentication.services.biometric_service import SyncBiometricService
from apps.authentication.models import UnifiedUser

logger = logging.getLogger("application")


class BiometricRegisterOptionsView(generics.GenericAPIView):
    """
    POST /api/v1/auth/biometric/register-options/
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        try:
            options, state = SyncBiometricService.generate_registration_options(
                request.user
            )
            request.session["biometric_reg_state"] = state
            return success_response(data=dict(options))
        except Exception as e:
            logger.warning("BiometricRegisterOptionsView: error=%s", e)
            return error_response(message=str(e), status=status.HTTP_400_BAD_REQUEST)


class BiometricRegisterVerifyView(generics.GenericAPIView):
    """
    POST /api/v1/auth/biometric/register-verify/
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        try:
            state = request.session.get("biometric_reg_state")
            if not state:
                return error_response(
                    message="State missing. Restart registration.",
                    status=status.HTTP_400_BAD_REQUEST,
                )

            SyncBiometricService.verify_registration_response(
                request.user,
                request,
                request.data,
                state,
                device_name=request.data.get("device_name", "Unknown Device"),
            )
            return success_response(message="Biometric registration successful.")
        except Exception as e:
            logger.warning("BiometricRegisterVerifyView: error=%s", e)
            return error_response(message=str(e), status=status.HTTP_400_BAD_REQUEST)


class BiometricLoginOptionsView(generics.GenericAPIView):
    """
    POST /api/v1/auth/biometric/login-options/
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        try:
            email = request.data.get("email")
            if not email:
                return error_response(
                    message="Email required.", status=status.HTTP_400_BAD_REQUEST
                )

            try:
                user = UnifiedUser.objects.get(email=email)
            except UnifiedUser.DoesNotExist:
                return error_response(
                    message="User not found.", status=status.HTTP_404_NOT_FOUND
                )

            options, state = SyncBiometricService.generate_auth_options(user)
            request.session["biometric_auth_state"] = state
            request.session["biometric_auth_user"] = str(
                user.id
            )  # Store UUID as string

            return success_response(data=dict(options))
        except Exception as e:
            logger.warning("BiometricLoginOptionsView: error=%s", e)
            return error_response(message=str(e), status=status.HTTP_400_BAD_REQUEST)


class BiometricLoginVerifyView(generics.GenericAPIView):
    """
    POST /api/v1/auth/biometric/login-verify/
    """

    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        try:
            state = request.session.get("biometric_auth_state")
            user_id = request.session.get("biometric_auth_user")

            if not state or not user_id:
                return error_response(
                    message="Session expired.", status=status.HTTP_400_BAD_REQUEST
                )

            user = UnifiedUser.objects.get(pk=user_id)
            SyncBiometricService.verify_auth_response(user, request, request.data, state)

            # Login successful, generate tokens
            from rest_framework_simplejwt.tokens import RefreshToken

            refresh = RefreshToken.for_user(user)
            tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}

            return success_response(data={"tokens": tokens}, message="Login Successful")
        except Exception as e:
            logger.warning("BiometricLoginVerifyView: error=%s", e)
            return error_response(message=str(e), status=status.HTTP_400_BAD_REQUEST)
