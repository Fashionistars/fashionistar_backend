"""
Synchronous password management views.

These views intentionally stay thin:
  - serializers validate request shape
  - SyncPasswordService owns business logic and audit behavior
  - views only translate service outcomes into stable API responses
"""

from __future__ import annotations

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BrowsableAPIRenderer

from apps.authentication.serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordResetRequestSerializer,
)
from apps.authentication.services.password_service import SyncPasswordService
from apps.common.permissions import (
    IsVerifiedUser,
    RateLimitPermission,
    require_verification,
)
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger("application")


def _frontend_url(path: str) -> str:
    """Build a stable frontend URL from the configured public origin."""
    return f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')}{path}"


@extend_schema(tags=["Authentication"])
class PasswordResetRequestView(generics.GenericAPIView):
    """Initiate an email- or phone-based password reset."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny, RateLimitPermission]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_scope = "password_reset"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = SyncPasswordService.request_reset(
                serializer.validated_data["email_or_phone"],
                request=request,
            )
        except Exception as exc:
            logger.error("PasswordResetRequest unexpected error: %s", exc, exc_info=True)
            message = "If an account exists, a reset code has been sent."

        return success_response(message=message, status=status.HTTP_200_OK)


@extend_schema(tags=["Authentication"])
class PasswordResetConfirmEmailView(generics.GenericAPIView):
    """Finalize an email reset flow using the link token."""

    serializer_class = PasswordResetConfirmEmailSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, uidb64, token, *args, **kwargs):
        serializer = self.get_serializer(
            data={**request.data, "uidb64": uidb64, "token": token}
        )
        serializer.is_valid(raise_exception=True)

        try:
            message = SyncPasswordService.confirm_reset(
                {
                    "uidb64": uidb64,
                    "token": token,
                    "new_password": serializer.validated_data["password"],
                },
                request=request,
            )
            return success_response(message=message, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.warning("PasswordResetConfirmEmail failed: %s", exc)
            return error_response(
                message="Invalid or expired reset link.",
                code="invalid_token",
                status=status.HTTP_400_BAD_REQUEST,
                errors={
                    "actions": {
                        "request_new_reset": "/api/v1/password/reset-request/",
                        "forgot_password_page": _frontend_url("/auth/forgot-password"),
                    }
                },
            )


@extend_schema(tags=["Authentication"])
class PasswordResetConfirmPhoneView(generics.GenericAPIView):
    """Finalize a phone reset flow using the OTP token."""

    serializer_class = PasswordResetConfirmPhoneSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = SyncPasswordService.confirm_reset(
                {
                    "token": serializer.validated_data["otp"],
                    "new_password": serializer.validated_data["new_password"],
                },
                request=request,
            )
            return success_response(message=message, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.warning("PasswordResetConfirmPhone failed: %s", exc)
            return error_response(
                message="Invalid or expired OTP.",
                code="invalid_otp",
                status=status.HTTP_400_BAD_REQUEST,
                errors={
                    "actions": {
                        "resend_otp": _frontend_url("/auth/forgot-password"),
                        "confirm_phone_page": _frontend_url(
                            "/auth/forgot-password/confirm-phone"
                        ),
                        "request_new_reset": "/api/v1/password/reset-request/",
                    }
                },
            )


@extend_schema(tags=["Authentication"])
class ChangePasswordView(generics.GenericAPIView):
    """Allow an authenticated verified user to change their password."""

    serializer_class = PasswordChangeSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @require_verification
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            message = SyncPasswordService.change_password(
                user=request.user,
                old_password=serializer.validated_data["old_password"],
                new_password=serializer.validated_data["new_password"],
                request=request,
            )
            return success_response(message=message, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error("ChangePassword failed: %s", exc, exc_info=True)
            detail = str(exc)
            if "current password is incorrect" in detail.lower():
                return error_response(
                    message=detail,
                    code="invalid_current_password",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return error_response(
                message="Unable to change password. Please try again.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
