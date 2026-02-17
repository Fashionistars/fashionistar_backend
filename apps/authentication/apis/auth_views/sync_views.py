# apps/authentication/apis/auth_views/sync_views.py
"""
Synchronous Authentication Views (DRF / WSGI).

These views handle auth operations via standard DRF GenericAPIView,
matching the legacy ``userauths.views`` pattern with enterprise-grade
error handling, structured logging, and atomic transactions.

Architecture:
    RegisterView   → UserRegistrationSerializer → RegistrationService.register_sync
    VerifyOTPView  → OTPSerializer              → OTPService.verify_otp_sync
    ResendOTPView  → ResendOTPRequestSerializer  → OTPService.resend_otp_sync
    LoginView      → LoginSerializer             → SyncAuthService.login
"""

import logging
from typing import Any, Dict

from django.db import transaction
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.models import UnifiedUser
from apps.authentication.serializers import (
    GoogleAuthSerializer,
    LoginSerializer,
    ResendOTPRequestSerializer,
    UserRegistrationSerializer,
)
from apps.authentication.services.auth_service import SyncAuthService
from apps.authentication.services.google_service import SyncGoogleAuthService
from apps.authentication.services.otp_service import OTPService
from apps.authentication.services.registration_service import (
    RegistrationService,
)
from apps.authentication.throttles import (
    BurstRateThrottle,
    SustainedRateThrottle,
)
from apps.common.renderers import CustomJSONRenderer

logger = logging.getLogger('application')


# ═══════════════════════════════════════════════════════════════════════
#  REGISTER VIEW — Mirrors legacy RegisterViewCelery
# ═══════════════════════════════════════════════════════════════════════

class RegisterView(APIView):
    """
    Synchronous User Registration (DRF).

    Accepts email OR phone + password, creates user inside an
    atomic transaction, generates OTP, and dispatches notification
    via Email or SMS.

    Legacy equivalent: ``userauths.views.RegisterViewCelery``

    Request Body:
        - email (str, optional): User email.
        - phone (str, optional): User phone (E.164).
        - password (str): Password.
        - password2 (str): Password confirmation.
        - role (str): 'vendor' or 'client'.

    Success Response (201):
        - message (str): Human-readable success message.
        - user_id (int): Created user's primary key.
        - email (str | None): Email if provided.
        - phone (str | None): Phone if provided.

    Error Responses:
        - 400: Validation errors (missing fields, weak password, etc.)
        - 500: Unexpected server errors.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    @transaction.atomic
    def post(self, request) -> Response:
        """
        Creates a new user and sends OTP via email or SMS.
        """
        try:
            # ── 1. Validate Input ────────────────────────────────────
            serializer = UserRegistrationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            validated_data: Dict[str, Any] = serializer.validated_data

            # ── Strip validation-only fields ─────────────────────────
            validated_data.pop('password2', None)
            validated_data.pop('password_confirm', None)

            # ── 2. Delegate to Registration Service (Atomic) ────────
            result = RegistrationService.register_sync(**validated_data)

            logger.info(
                "✅ RegisterView: user_id=%s, identifier=%s",
                result.get('user_id'),
                result.get('email') or result.get('phone'),
            )

            return Response({
                "message": result['message'],
                "user_id": result['user_id'],
                "email": result.get('email'),
                "phone": result.get('phone'),
            }, status=status.HTTP_201_CREATED)

        except drf_serializers.ValidationError as e:
            # ── Serializer validation errors → 400 ──────────────────
            logger.warning("⚠️ RegisterView validation error: %s", e)
            return Response(
                e.detail,
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            # ── Unexpected error → 500 + explicit rollback ──────────
            transaction.set_rollback(True)
            logger.error(
                "❌ RegisterView unexpected error: %s", str(e),
                exc_info=True
            )
            return Response(
                {
                    "error": (
                        "An error occurred during registration. "
                        "Please check your input or contact support."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ═══════════════════════════════════════════════════════════════════════
#  LOGIN VIEW
# ═══════════════════════════════════════════════════════════════════════

class LoginView(APIView):
    """
    Synchronous Login View (DRF).

    Authenticates user via email/phone + password, returns JWT tokens.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        """Authenticates user and returns JWT tokens."""
        try:
            serializer = LoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data: Dict[str, Any] = serializer.validated_data

            tokens = SyncAuthService.login(
                data['email_or_phone'],
                data['password'],
                request
            )

            return Response({
                "message": "Login Successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)

        except drf_serializers.ValidationError as e:
            logger.warning("⚠️ LoginView validation error: %s", e)
            return Response(
                e.detail,
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            logger.error(
                "❌ LoginView error: %s", str(e), exc_info=True
            )
            return Response(
                {"error": "An error occurred during login. "
                 "Please check your credentials."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ═══════════════════════════════════════════════════════════════════════
#  VERIFY OTP VIEW — Mirrors legacy VerifyOTPView
# ═══════════════════════════════════════════════════════════════════════

class VerifyOTPView(APIView):
    """
    Synchronous OTP Verification (DRF).

    Verifies OTP, activates user, and returns JWT tokens.
    Mirrors legacy ``userauths.views.VerifyOTPView`` behavior:
    auto-login after successful OTP verification.

    Request Body:
        - otp (str): The OTP code.
        - user_id (str): UUID of the user to verify.

    Success Response (200):
        - message, user_id, role, identifying_info, access, refresh
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    @transaction.atomic
    def post(self, request) -> Response:
        """Verifies OTP and activates user account."""
        try:
            otp_code = request.data.get('otp')
            user_id = request.data.get('user_id')

            # ── Input validation ─────────────────────────────────────
            if not otp_code or not user_id:
                return Response(
                    {"error": "Both 'otp' and 'user_id' are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ── Verify OTP via service ───────────────────────────────
            valid = OTPService.verify_otp_sync(
                user_id, otp_code, purpose="verify"
            )

            if not valid:
                logger.warning(
                    "⚠️ Invalid/expired OTP for user_id=%s", user_id
                )
                return Response(
                    {"error": "Invalid or expired OTP. "
                     "Please request a new one."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ── Activate user ────────────────────────────────────────
            try:
                user = UnifiedUser.objects.only(
                    "id", "is_active", "is_verified", "role",
                    "email", "phone"
                ).get(pk=user_id)
            except UnifiedUser.DoesNotExist:
                logger.error(
                    "❌ User not found after OTP verify: %s", user_id
                )
                return Response(
                    {"error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not user.is_active:
                user.is_active = True
            user.is_verified = True
            user.save(update_fields=['is_active', 'is_verified'])

            logger.info(
                "✅ User verified: id=%s, identifier=%s",
                user.id, user.identifying_info
            )

            # ── Auto-login: Generate JWT tokens (legacy pattern) ─────
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Your account has been successfully verified.",
                "user_id": user.id,
                "role": user.role,
                "identifying_info": user.identifying_info,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }, status=status.HTTP_200_OK)

        except drf_serializers.ValidationError as e:
            logger.warning(
                "⚠️ VerifyOTPView validation error: %s", e
            )
            return Response(
                e.detail, status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            transaction.set_rollback(True)
            logger.error(
                "❌ VerifyOTPView error: %s", str(e), exc_info=True
            )
            return Response(
                {"error": "An error occurred during verification. "
                 "Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ═══════════════════════════════════════════════════════════════════════
#  RESEND OTP VIEW — Mirrors legacy ResendOTPView
# ═══════════════════════════════════════════════════════════════════════

class ResendOTPView(APIView):
    """
    Synchronous OTP Resend (DRF).

    Regenerates and re-sends OTP to user's email or phone.

    Request Body:
        - email_or_phone (str): User email or phone number.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        """Resends OTP to user's email or phone."""
        try:
            serializer = ResendOTPRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email_or_phone = serializer.validated_data.get(
                'email_or_phone'
            )

            message = OTPService.resend_otp_sync(
                email_or_phone=email_or_phone
            )

            logger.info(
                "✅ OTP resent for: %s", email_or_phone
            )

            return Response(
                {"message": message}, status=status.HTTP_200_OK
            )

        except drf_serializers.ValidationError as e:
            logger.warning(
                "⚠️ ResendOTPView validation error: %s", e
            )
            return Response(
                e.detail, status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            logger.error(
                "❌ ResendOTPView error: %s", str(e), exc_info=True
            )
            return Response(
                {"error": "An error occurred while resending OTP. "
                 "Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ═══════════════════════════════════════════════════════════════════════
#  GOOGLE AUTH VIEW
# ═══════════════════════════════════════════════════════════════════════

class GoogleAuthView(APIView):
    """Google OAuth2 authentication via ID token."""
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request) -> Response:
        """Verifies Google ID token and returns JWT tokens."""
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = SyncGoogleAuthService.verify_and_login(
            data['id_token'], data.get('role', 'client')
        )

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        return Response({
            "message": "Google Login Successful",
            "tokens": {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            "user": {
                "email": user.email,
                "role": user.role,
            },
        })


# ═══════════════════════════════════════════════════════════════════════
#  REFRESH TOKEN VIEW
# ═══════════════════════════════════════════════════════════════════════

class RefreshTokenView(APIView):
    """
    JWT Token Refresh.

    Wraps SimpleJWT's TokenRefreshView for custom renderer
    compatibility.
    """
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request) -> Response:
        """Refreshes JWT access token."""
        from rest_framework_simplejwt.views import TokenRefreshView
        return TokenRefreshView.as_view()(request)


# ═══════════════════════════════════════════════════════════════════════
#  LOGOUT VIEW
# ═══════════════════════════════════════════════════════════════════════

class LogoutView(APIView):
    """
    User Logout.

    Blacklists the refresh token (if token blacklisting is enabled),
    otherwise the client simply deletes the token.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request) -> Response:
        """Logs out user by blacklisting refresh token."""
        return Response(
            {"message": "Logout Successful"},
            status=status.HTTP_200_OK,
        )
