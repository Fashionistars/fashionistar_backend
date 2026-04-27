# apps/authentication/apis/auth_views/sync_views.py
"""
Authentication Views — Synchronous DRF (WSGI)
=============================================

Primary authentication gateway for FASHIONISTAR.
Handles Registration, Login, OTP Verification, and Session Management.
"""

import logging
from typing import Any, Dict

from django.conf import settings as _s
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import OperationalError as DbOperationalError, transaction
from rest_framework import generics, serializers as drf_serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.authentication.models import UnifiedUser
from apps.authentication.serializers import (
    LoginSerializer,
    LogoutSerializer,
    ResendOTPRequestSerializer,
    TokenRefreshSerializer,
    UserRegistrationSerializer,
    OTPSerializer,
)
from apps.authentication.services.auth_service import SyncAuthService
from apps.authentication.services.otp import OTPService
from apps.authentication.services.profile_service.profile_service import get_post_auth_state
from apps.authentication.services.registration import RegistrationService
from apps.authentication.throttles import BurstRateThrottle, SustainedRateThrottle
from apps.authentication.serializers.auth import (
    RegistrationResponseSerializer,
    LoginResponseSerializer,
    OTPVerifyResponseSerializer,
)
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from drf_spectacular.utils import extend_schema

logger = logging.getLogger('application')


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================


def _set_refresh_cookie(response, refresh_token_str: str) -> None:
    """
    Split-token pattern (Auth0 / Supabase style):
      - Access token  → JSON body + sessionStorage (short-lived)
      - Refresh token → HttpOnly cookie (long-lived, NOT accessible by JS)
    """
    max_age = getattr(_s, 'REFRESH_TOKEN_COOKIE_MAX_AGE', 60 * 60 * 24 * 30)
    cookie_name = getattr(_s, 'REFRESH_TOKEN_COOKIE_NAME', 'fashionistar_rt')
    cookie_samesite = getattr(_s, 'REFRESH_TOKEN_COOKIE_SAMESITE', 'Lax')
    cookie_secure = getattr(_s, 'REFRESH_TOKEN_COOKIE_SECURE', not _s.DEBUG)
    cookie_domain = getattr(_s, 'REFRESH_TOKEN_COOKIE_DOMAIN', None)
    response.set_cookie(
        key=cookie_name,
        value=refresh_token_str,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        domain=cookie_domain,
        path='/',
    )


def _clear_refresh_cookie(response) -> None:
    """Remove the refresh token cookie on logout."""
    cookie_name = getattr(_s, 'REFRESH_TOKEN_COOKIE_NAME', 'fashionistar_rt')
    cookie_samesite = getattr(_s, 'REFRESH_TOKEN_COOKIE_SAMESITE', 'Lax')
    cookie_domain = getattr(_s, 'REFRESH_TOKEN_COOKIE_DOMAIN', None)
    response.delete_cookie(cookie_name, path='/', samesite=cookie_samesite, domain=cookie_domain)


def _build_auth_response_state(user: UnifiedUser) -> Dict[str, Any]:
    """Compile post-authentication state for the user."""
    return get_post_auth_state(user=user)


def _get_refresh_from_request(request) -> str | None:
    """
    Resolve refresh token from request body first, then HttpOnly cookie.

    Body token support is retained for backward compatibility.
    Preferred production path is HttpOnly cookie transport.
    """
    body_refresh = request.data.get("refresh")
    if body_refresh:
        return body_refresh

    cookie_name = getattr(_s, 'REFRESH_TOKEN_COOKIE_NAME', 'fashionistar_rt')
    return request.COOKIES.get(cookie_name)


# ===========================================================================
# POST /api/v1/auth/register/
# ===========================================================================


class RegisterView(generics.CreateAPIView):
    """
    Register a new user account with OTP verification.

    Flow:
      1. Accept email/phone, password, and role (vendor/client).
      2. Perform atomic user creation in the database.
      3. Generate a 6-digit OTP and cache it in Redis.
      4. Trigger asynchronous dispatch of OTP via Email or SMS.

    Legacy Context:
      Replaces and extends `userauths.views.RegisterViewCelery`.

    Status Codes:
      - 201 Created: Registration successful, OTP dispatched.
      - 400 Bad Request: Validation errors (email exists, weak password).
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes = [BurstRateThrottle]

    @extend_schema(
        responses={201: RegistrationResponseSerializer},
        summary="Register a new user",
        description="Creates a new user account and sends an OTP for verification."
    )
    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.perform_create(serializer)

    @transaction.atomic
    def perform_create(self, serializer) -> Response:
        try:
            validated_data: Dict[str, Any] = dict(serializer.validated_data)
            validated_data.pop('password2', None)
            validated_data.pop('password_confirm', None)

            result = RegistrationService.register_sync(**validated_data)

            logger.info("✅ RegisterView: user_id=%s identifier=%s", result.get('user_id'), result.get('email') or result.get('phone'))

            return success_response(
                data={
                    "user_id": result['user_id'],
                    "email": result.get('email'),
                    "phone": result.get('phone'),
                },
                message=result['message'],
                status=status.HTTP_201_CREATED,
            )

        except drf_serializers.ValidationError as exc:
            logger.warning("⚠️ RegisterView DRF validation error: %s", exc.detail)
            return error_response(message="Validation failed", errors=exc.detail, status=status.HTTP_400_BAD_REQUEST)

        except DjangoValidationError as exc:
            transaction.set_rollback(True)
            error_detail = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
            flat = {field: msgs[0] if isinstance(msgs, list) and len(msgs) == 1 else msgs for field, msgs in error_detail.items()}
            logger.warning("⚠️ RegisterView model validation error: %s", flat)
            return error_response(message="Registration validation error", errors=flat, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            transaction.set_rollback(True)
            logger.error("❌ RegisterView error: %s", str(exc), exc_info=True)
            return error_response(message="Registration failed. Please try again.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# POST /api/v1/auth/login/
# ===========================================================================


class LoginView(generics.GenericAPIView):
    """
    Authenticate user and issue JWT session tokens.

    Flow:
      1. Validate credentials (email/phone + password).
      2. Check account status (verified, active, not soft-deleted).
      3. Record LoginEvent and trigger audit logging.
      4. Issue access token (JSON) and refresh token (HttpOnly Cookie).

    Audit & Compliance:
      Every attempt is logged in `LoginEvent` with IP and UserAgent details.

    Status Codes:
      - 200 OK: Authentication successful.
      - 401 Unauthorized: Invalid credentials.
      - 403 Forbidden: Account unverified or deactivated.
    """
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    @extend_schema(
        responses={200: LoginResponseSerializer},
        summary="Login user",
        description="Authenticates user and returns JWT tokens + HttpOnly cookie."
    )
    def post(self, request, *args, **kwargs) -> Response:
        from apps.authentication.exceptions import (
            SoftDeletedUserError, AccountNotVerifiedError,
            AccountDeactivatedError, AccountInactiveError,
            InvalidCredentialsError,
        )
        try:
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                raise drf_serializers.ValidationError(serializer.errors)

            result = SyncAuthService.login(
                email_or_phone=serializer.validated_data.get('email_or_phone'),
                password=serializer.validated_data.get('password'),
                request=request,
            )
            user = result['user']
            auth_state = _build_auth_response_state(user)

            logger.info("✅ LoginView: login successful for %s", user.identifying_info)

            response = success_response(
                data={
                    "user_id": str(user.id),
                    "role": user.role,
                    "identifying_info": user.identifying_info,
                    "access": result['access'],
                    # Backward compatibility: legacy clients still read refresh in JSON.
                    "refresh": result["refresh"],
                    # Backward compatibility: some clients/tests read message from payload.
                    "message": "Login successful.",
                    **auth_state,
                },
                message="Login successful.",
                status=status.HTTP_200_OK,
            )
            _set_refresh_cookie(response, result['refresh'])
            return response

        except SoftDeletedUserError as exc:
            return error_response(message=str(exc.detail), code=exc.default_code, status=status.HTTP_403_FORBIDDEN)
        except AccountNotVerifiedError as exc:
            return error_response(message=str(exc.detail), code=exc.default_code, status=status.HTTP_403_FORBIDDEN)
        except (AccountDeactivatedError, AccountInactiveError) as exc:
            return error_response(message=str(exc.detail), code=exc.default_code, status=status.HTTP_403_FORBIDDEN)
        except InvalidCredentialsError as exc:
            return error_response(message=str(exc.detail), code=exc.default_code, status=status.HTTP_401_UNAUTHORIZED)
        except drf_serializers.ValidationError as exc:
            return error_response(message="Validation failed", errors=exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("❌ LoginView unexpected error: %s", str(exc), exc_info=True)
            return error_response(message="Login failed. Please try again.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# POST /api/v1/auth/verify-otp/
# ===========================================================================


class VerifyOTPView(generics.GenericAPIView):
    """
    Verify the 6-digit OTP code and activate the user account.

    Flow:
      1. Accept OTP code (O(1) Redis lookup by hash).
      2. Identify the user ID associated with the OTP.
      3. Activate the user (is_verified=True, is_active=True).
      4. Auto-issue JWT session tokens on successful verification.

    Security:
      One-time use. OTP is deleted from Redis immediately upon verification.

    Status Codes:
      - 200 OK: Verification successful, account activated.
      - 400 Bad Request: Invalid or expired OTP.
    """
    serializer_class = OTPSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes = [BurstRateThrottle]

    @extend_schema(
        responses={200: OTPVerifyResponseSerializer},
        summary="Verify OTP",
        description="Verifies the 6-digit OTP code and activates user account."
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp_code = serializer.validated_data['otp']

            result = OTPService.verify_by_otp_sync(otp_code, purpose='verify')
            if not result:
                return error_response(message="Invalid or expired OTP.", status=status.HTTP_400_BAD_REQUEST)

            user_id = result['user_id']
            try:
                user = UnifiedUser.objects.get(pk=user_id)
            except UnifiedUser.DoesNotExist:
                return error_response(message="User not found.", status=status.HTTP_404_NOT_FOUND)

            # Activate account
            user.is_active = True
            user.is_verified = True
            user.save(update_fields=['is_active', 'is_verified'])

            from apps.common.events import event_bus
            event_bus.emit_on_commit("user.verified", user_uuid=str(user.id), role=user.role)

            logger.info("✅ Account verified: id=%s", user.id)

            from rest_framework_simplejwt.tokens import RefreshToken
            from django.contrib.auth.models import update_last_login
            refresh = RefreshToken.for_user(user)
            update_last_login(None, user)
            auth_state = _build_auth_response_state(user)

            response = success_response(
                data={
                    "user_id": str(user.id),
                    "role": user.role,
                    "identifying_info": user.identifying_info,
                    "access": str(refresh.access_token),
                    **auth_state,
                },
                message="Account successfully verified.",
                status=status.HTTP_200_OK,
            )
            if getattr(_s, "AUTH_INCLUDE_REFRESH_IN_BODY", False):
                response.data["data"]["refresh"] = str(refresh)
            _set_refresh_cookie(response, str(refresh))
            return response

        except drf_serializers.ValidationError as exc:
            return error_response(
                message="Validation failed",
                errors=exc.detail,
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            transaction.set_rollback(True)
            logger.error("❌ VerifyOTPView unexpected error: %s", str(exc), exc_info=True)
            return error_response(message="Verification failed.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# POST /api/v1/auth/resend-otp/
# ===========================================================================


class ResendOTPView(generics.GenericAPIView):
    """
    Regenerate and resend a 6-digit OTP code.

    Flow:
      1. Validate user existence by email or phone.
      2. Regenerate a new secure OTP code.
      3. Dispatch via the primary communication channel.

    Status Codes:
      - 200 OK: OTP resent successfully.
      - 400 Bad Request: Validation or throttled request.
    """
    serializer_class = ResendOTPRequestSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes = [BurstRateThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            msg = OTPService.resend_otp_sync(email_or_phone=serializer.validated_data.get('email_or_phone'))
            return success_response(message=msg, status=status.HTTP_200_OK)

        except drf_serializers.ValidationError as exc:
            return error_response(
                message="Validation failed",
                errors=exc.detail,
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.error("❌ ResendOTPView error: %s", str(exc), exc_info=True)
            return error_response(message="Failed to resend OTP.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# POST /api/v1/auth/token/refresh/
# ===========================================================================


class RefreshTokenView(generics.GenericAPIView):
    """
    Refresh JWT access tokens using the stored refresh token.

    Flow:
      1. Extract refresh token from request body (or HttpOnly cookie).
      2. Verify refresh token validity via SimpleJWT.
      3. Issue new short-lived access token.

    Status Codes:
      - 200 OK: Access token refreshed.
      - 401 Unauthorized: Invalid or expired refresh token.
    """
    serializer_class = TokenRefreshSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        from rest_framework_simplejwt.serializers import TokenRefreshSerializer as SimpleJWTTokenRefreshSerializer
        from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

        try:
            refresh_token = _get_refresh_from_request(request)
            if not refresh_token:
                return error_response(
                    message="Refresh token required.",
                    status=status.HTTP_400_BAD_REQUEST,
                )

            serializer = SimpleJWTTokenRefreshSerializer(data={"refresh": refresh_token})
            serializer.is_valid(raise_exception=True)

            refreshed_data = dict(serializer.validated_data)
            response = success_response(data=refreshed_data, message="Token refreshed.")

            # If rotation is enabled, persist the newly-issued refresh token cookie.
            rotated_refresh = refreshed_data.get("refresh")
            if rotated_refresh:
                _set_refresh_cookie(response, rotated_refresh)
            return response
        except (TokenError, InvalidToken):
            response = error_response(message="Token invalid or expired.", status=status.HTTP_401_UNAUTHORIZED)
            _clear_refresh_cookie(response)
            return response
        except Exception:
            logger.error("RefreshTokenView unexpected error", exc_info=True)
            return error_response(message="Refresh failed.", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# POST /api/v1/auth/logout/
# ===========================================================================


class LogoutView(generics.GenericAPIView):
    """
    Terminate the user session and blacklist the refresh token.

    Flow:
      1. Accept current refresh token.
      2. Blacklist the token in the database to prevent reuse.
      3. Clear the HttpOnly session cookie.

    Status Codes:
      - 200 OK: Logout successful.
      - 401 Unauthorized: Not authenticated.
    """
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError

        try:
            refresh_token = _get_refresh_from_request(request)
            if not refresh_token:
                return error_response(message="Refresh token required.", status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                token = RefreshToken(refresh_token)
                token.blacklist()

            logger.info(
                "Logout: refresh token blacklisted — user_id=%s",
                request.user.id,
            )
            response = success_response(
                message="Logout Successful. Your session has been terminated.",
                status=status.HTTP_200_OK,
            )
            _clear_refresh_cookie(response)  # Invalidate HttpOnly cookie
            return response

        except TokenError as exc:
            logger.warning(
                "LogoutView TokenError user_id=%s: %s",
                getattr(request.user, 'id', 'anon'), str(exc),
            )
            return error_response(
                message="Token is already invalid or has expired.",
                status=status.HTTP_400_BAD_REQUEST
            )

        except DbOperationalError as exc:
            # Handle DB table lock (can occur under extreme concurrent load on
            # SQLite dev environments; PostgreSQL in production uses row-level
            # locks, so this is an extremely rare edge case in prod).
            logger.warning(
                "LogoutView DB lock on blacklist (concurrent request) user_id=%s: %s",
                getattr(request.user, 'id', 'anon'), str(exc),
            )
            resp = error_response(
                message="Server busy. Please retry logout in a moment.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
            resp["Retry-After"] = "1"
            return resp

        except Exception as exc:
            logger.error(
                "LogoutView unexpected error: %s", str(exc), exc_info=True
            )
            return error_response(
                message="An error occurred during logout. Please try again.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



