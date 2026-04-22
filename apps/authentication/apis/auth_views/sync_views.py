# apps/authentication/apis/auth_views/sync_views.py
"""
FASHIONISTAR — Synchronous Authentication Views (DRF / WSGI)
=============================================================

All views use DRF generics pattern (generics.CreateAPIView /
generics.GenericAPIView) — exactly like the legacy
``userauths.views.RegisterViewCelery`` pattern the user requires.

Architecture:
    RegisterView     → generics.CreateAPIView   → RegistrationService.register_sync
    VerifyOTPView    → generics.GenericAPIView   → OTPService.verify_otp_sync
    ResendOTPView    → generics.GenericAPIView   → OTPService.resend_otp_sync
    LoginView        → generics.GenericAPIView   → SyncAuthService.login
    GoogleAuthView   → generics.CreateAPIView    → SyncGoogleAuthService.verify_and_login
    RefreshTokenView → generics.GenericAPIView   → SimpleJWT TokenRefreshView
    LogoutView       → generics.GenericAPIView   → RefreshToken.blacklist()

Why generics over APIView?
  - get_serializer() / get_serializer_class() hooks work out of the box
  - Schema generation (drf-spectacular) picks up serializer automatically
  - Consistent behaviour with the entire rest of the codebase (legacy pattern)
  - CreateAPIView.create() provides a standardised perform_create() override point
  - DRF browsable API renders the correct form fields automatically
"""

import logging
from typing import Any, Dict

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import generics, serializers as drf_serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.authentication.models import UnifiedUser
from apps.authentication.serializers import (
    GoogleAuthSerializer,
    LoginSerializer,
    LogoutSerializer,
    ResendOTPRequestSerializer,
    TokenRefreshSerializer,
    UserRegistrationSerializer,
    OTPSerializer,
)
from apps.authentication.services.auth_service import SyncAuthService
from apps.authentication.services.google_service import SyncGoogleAuthService
from apps.authentication.services.otp import OTPService
from apps.authentication.services.profile_service.profile_service import (
    get_post_auth_state,
)
from apps.authentication.services.registration import RegistrationService
from apps.authentication.throttles import BurstRateThrottle, SustainedRateThrottle
from apps.common.renderers import CustomJSONRenderer

logger = logging.getLogger(__name__)


def _build_auth_response_state(user: UnifiedUser) -> Dict[str, Any]:
    return get_post_auth_state(user=user)


# ═══════════════════════════════════════════════════════════════════════════
#  REGISTER VIEW — mirrors legacy RegisterViewCelery
# ═══════════════════════════════════════════════════════════════════════════

class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/

    Synchronous User Registration.

    Accepts email OR phone + password + role, creates the user inside an
    atomic transaction, generates a 6-digit OTP, and dispatches it via
    Email (if email provided) or SMS (if phone only).

    Mirrors legacy:  ``userauths.views.RegisterViewCelery``

    Request Body:
        email     (str, optional)  : User email address.
        phone     (str, optional)  : Phone in E.164 format (+234...).
        password  (str, required)  : Min 8 chars, must contain upper/lower/digit/special.
        password2 (str, required)  : Must match password.
        role      (str, required)  : 'vendor' or 'client'.

    Success Response 201:
        {
          "message": "Registration successful. Check your email/phone for OTP.",
          "user_id": "<uuid>",
          "email":   "user@example.com",
          "phone":   null
        }

    Error Responses:
        400 — Validation error (missing fields, weak password, mismatch, duplicate)
        500 — Unexpected server error (transaction rolled back)
    """
    serializer_class    = UserRegistrationSerializer
    permission_classes  = [AllowAny]
    renderer_classes    = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes    = [BurstRateThrottle]

    def create(self, request, *args, **kwargs) -> Response:
        """
        Override generics.CreateAPIView.create() to:
          1. Validate via UserRegistrationSerializer
          2. Delegate to RegistrationService (inside atomic transaction)
          3. Return a structured 201 response
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.perform_create(serializer)

    @transaction.atomic
    def perform_create(self, serializer) -> Response:  # type: ignore[override]
        """Atomic user creation + OTP dispatch."""
        try:
            validated_data: Dict[str, Any] = dict(serializer.validated_data)

            # Strip validation-only fields (not passed to the service)
            validated_data.pop('password2', None)
            validated_data.pop('password_confirm', None)

            result = RegistrationService.register_sync(**validated_data)

            logger.info(
                "✅ RegisterView: user_id=%s identifier=%s",
                result.get('user_id'),
                result.get('email') or result.get('phone'),
            )

            return Response(
                {
                    "message": result['message'],
                    "user_id": result['user_id'],
                    "email":   result.get('email'),
                    "phone":   result.get('phone'),
                },
                status=status.HTTP_201_CREATED,
            )

        except drf_serializers.ValidationError as exc:
            # DRF serializer-level validation errors (from UserRegistrationSerializer)
            logger.warning("⚠️ RegisterView DRF validation error: %s", exc.detail)
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        except DjangoValidationError as exc:
            # django.core.exceptions.ValidationError from model.full_clean()
            # Triggered e.g. when a concurrent request sneaks past the serializer
            # uniqueness check and the DB unique constraint fires on save().
            # Convert to a clean 400 with human-readable field errors.
            transaction.set_rollback(True)
            if hasattr(exc, 'message_dict'):
                error_detail = exc.message_dict   # {'email': ['Already exists.']}
            else:
                error_detail = {'error': exc.messages}
            # Flatten single-item lists for cleaner UX
            flat = {
                field: msgs[0] if isinstance(msgs, list) and len(msgs) == 1 else msgs
                for field, msgs in error_detail.items()
            }
            logger.warning(
                "⚠️ RegisterView model validation error (duplicate/race-condition): %s",
                flat,
            )
            return Response(flat, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            transaction.set_rollback(True)
            logger.error("❌ RegisterView error: %s", str(exc), exc_info=True)
            return Response(
                {
                    "error": (
                        "An error occurred during registration. "
                        "Please verify your input or contact support."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ═══════════════════════════════════════════════════════════════════════════
#  LOGIN VIEW
# ═══════════════════════════════════════════════════════════════════════════

class LoginView(generics.GenericAPIView):
    """
    POST /api/v1/auth/login/

    Synchronous Login — email/phone + password → JWT tokens.

    Request Body:
        email_or_phone (str): Registered email or international phone number.
        password       (str): User password.

    Success Response 200:
        {
          "message": "Login Successful",
          "user_id": "<uuid>",
          "role":    "client",
          "identifying_info": "user@example.com",
          "access":  "<JWT access token>",
          "refresh": "<JWT refresh token>"
        }

    Error Responses:
        400 — Validation error or wrong credentials
        403 — User not verified / account inactive
        500 — Unexpected server error
    """
    serializer_class   = LoginSerializer
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes   = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        """
        Full enterprise-grade login via SyncAuthService.

        SyncAuthService.login() performs (in order):
          1. Soft-delete pre-check → SoftDeletedUserError (403)
          2. Django authenticate() → password verification
          3. is_verified check    → AccountNotVerifiedError (403) with OTP URLs
          4. is_active check      → AccountDeactivatedError (403) with support URL
          5. Invalid credentials  → InvalidCredentialsError (401)
          6. LoginEvent INSERT (every attempt — success AND failure)
          7. AuditService.log()  (async via Celery on_commit)
          8. UserSession.create_from_token() via transaction.on_commit()
          9. lifecycle_counter Celery task (fire-and-forget)

        This provides a complete, tamper-proof audit trail for every login
        attempt — critical for SIEM dashboards and compliance requirements.
        """
        from apps.authentication.exceptions import (
            SoftDeletedUserError,
            AccountNotVerifiedError,
            AccountDeactivatedError,
            InvalidCredentialsError,
        )
        try:
            # ── Step 1: Field validation (email_or_phone + password format) ──
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                raise drf_serializers.ValidationError(serializer.errors)

            email_or_phone = serializer.validated_data.get('email_or_phone')
            password       = serializer.validated_data.get('password')

            # ── Step 2: Full audit-logged auth via SyncAuthService ───────────
            # This is where LoginEvent, UserSession, AuditLog are ALL recorded.
            # SyncAuthService.login() raises typed exceptions for every failure.
            result = SyncAuthService.login(
                email_or_phone=email_or_phone,
                password=password,
                request=request,
            )
            user = result['user']
            auth_state = _build_auth_response_state(user)

            logger.info(
                "✅ LoginView: login successful for %s (id=%s role=%s)",
                user.identifying_info, user.id, user.role,
            )

            return Response(
                {
                    "message":          "Login successful.",
                    "user_id":          str(user.id),
                    "role":             user.role,
                    "identifying_info": user.identifying_info,
                    "access":           result['access'],
                    "refresh":          result['refresh'],
                    **auth_state,
                },
                status=status.HTTP_200_OK,
            )

        except SoftDeletedUserError as exc:
            logger.warning(
                "⛔ LoginView: soft-deleted account attempt — %s",
                request.data.get('email_or_phone', ''),
            )
            return Response(
                {"success": False, "message": str(exc.detail), "code": exc.default_code},
                status=status.HTTP_403_FORBIDDEN,
            )

        except AccountNotVerifiedError as exc:
            logger.warning(
                "⛔ LoginView: unverified account attempt — %s",
                request.data.get('email_or_phone', ''),
            )
            return Response(
                {"success": False, "message": str(exc.detail), "code": exc.default_code},
                status=status.HTTP_403_FORBIDDEN,
            )

        except AccountDeactivatedError as exc:
            logger.warning(
                "⛔ LoginView: deactivated account attempt — %s",
                request.data.get('email_or_phone', ''),
            )
            return Response(
                {"success": False, "message": str(exc.detail), "code": exc.default_code},
                status=status.HTTP_403_FORBIDDEN,
            )

        except InvalidCredentialsError as exc:
            return Response(
                {"success": False, "message": str(exc.detail), "code": exc.default_code},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        except drf_serializers.ValidationError as exc:
            logger.warning("⚠️ LoginView validation error: %s", exc.detail)
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            logger.error(
                "❌ LoginView unexpected error: %s", str(exc), exc_info=True
            )
            return Response(
                {"success": False, "error": "An error occurred during login. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



# ═══════════════════════════════════════════════════════════════════════════
#  VERIFY OTP VIEW — mirrors legacy VerifyOTPView
# ═══════════════════════════════════════════════════════════════════════════

class VerifyOTPView(generics.GenericAPIView):
    """
    POST /api/v1/auth/verify-otp/

    Synchronous OTP Verification.

    Mirrors the legacy VerifyOTPView pattern exactly:
      - Client sends ONLY the 6-digit OTP code (no user_id in request).
      - Server discovers the user via O(1) SHA-256 hash index in Redis.
      - Activates the account (is_active=True, is_verified=True).
      - Auto-issues JWT access + refresh tokens on success.

    Request Body:
        otp (str): 6-digit OTP code received via email or SMS.

    Success Response 200:
        {
          "message": "Your account has been successfully verified.",
          "user_id": "<uuid>",
          "role":    "client",
          "identifying_info": "user@example.com",
          "access":  "<JWT>",
          "refresh": "<JWT>"
        }

    Error Responses:
        400 — Missing OTP, invalid / expired OTP
        404 — User not found (OTP valid but user deleted mid-flow)
        503 — Redis unavailable
        500 — Unexpected server error
    """
    serializer_class   = OTPSerializer
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes   = [BurstRateThrottle]

    @transaction.atomic
    def post(self, request, *args, **kwargs) -> Response:
        """
        Verifies OTP (OTP-only, no user_id in request) and issues JWT tokens.

        Flow:
          1. Validate OTP format via OTPSerializer (6-digit numeric).
          2. OTPService.verify_by_otp_sync():
               - SHA-256 hash the submitted OTP.
               - O(1) Redis GET otp_hash:{hash} → primary_key.
               - Parse user_id from primary_key.
               - TTL-guard: verify primary key still alive.
               - Atomic DEL both keys (one-time use).
               - Returns {'user_id': ..., 'purpose': ...} or None.
          3. Fetch User from DB using discovered user_id.
          4. Activate account: is_active=True, is_verified=True.
          5. Issue JWT tokens → return full response.

        Mirrors legacy VerifyOTPView — client only needs the OTP code.
        """
        try:
            # Step 1 — Validate OTP format via serializer
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp_code = serializer.validated_data['otp']

            # Step 2 — O(1) Redis lookup: OTP → user_id (no scan, no user_id needed)
            result = OTPService.verify_by_otp_sync(otp_code, purpose='verify')
            if not result:
                logger.warning("⚠️ VerifyOTPView: invalid/expired OTP submitted")
                return Response(
                    {"error": "Invalid or expired OTP. Please request a new one."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user_id = result['user_id']

            # Step 3 — Fetch User from DB
            try:
                user = UnifiedUser.objects.only(
                    "id", "is_active", "is_verified", "role", "email", "phone"
                ).get(pk=user_id)
            except UnifiedUser.DoesNotExist:
                logger.error(
                    "❌ VerifyOTPView: user not found after OTP verify: %s", user_id
                )
                return Response(
                    {"error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Step 4 — Activate account
            changed = []
            if not user.is_active:
                user.is_active   = True
                changed.append('is_active')
            if not user.is_verified:
                user.is_verified = True
                changed.append('is_verified')
            if changed:
                user.save(update_fields=changed)

            from apps.common.events import event_bus
            event_bus.emit_on_commit(
                "user.verified",
                user_uuid=str(user.id),
                role=str(user.role or ""),
                email=str(user.email) if user.email else None,
                phone=str(user.phone) if user.phone else None,
            )

            logger.info(
                "✅ Account verified: id=%s identifier=%s",
                user.id, user.identifying_info,
            )

            # Step 5 — Issue JWT tokens
            from rest_framework_simplejwt.tokens import RefreshToken
            from django.contrib.auth.models import update_last_login
            refresh = RefreshToken.for_user(user)
            update_last_login(None, user)
            auth_state = _build_auth_response_state(user)

            return Response(
                {
                    "message":          "Your account has been successfully verified.",
                    "user_id":          str(user.id),
                    "role":             user.role,
                    "identifying_info": user.identifying_info,
                    "access":           str(refresh.access_token),
                    "refresh":          str(refresh),
                    **auth_state,
                },
                status=status.HTTP_200_OK,
            )

        except drf_serializers.ValidationError as exc:
            logger.warning("⚠️ VerifyOTPView validation error: %s", exc.detail)
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            transaction.set_rollback(True)
            logger.error(
                "❌ VerifyOTPView unexpected error: %s", str(exc), exc_info=True
            )
            return Response(
                {"error": "Verification failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



# ═══════════════════════════════════════════════════════════════════════════
#  RESEND OTP VIEW — mirrors legacy ResendOTPView
# ═══════════════════════════════════════════════════════════════════════════

class ResendOTPView(generics.GenericAPIView):
    """
    POST /api/v1/auth/resend-otp/

    Regenerates and resends OTP via email or SMS.

    Request Body:
        email_or_phone (str): Registered email or phone number.

    Success Response 200:
        { "message": "OTP resent successfully." }
    """
    serializer_class   = ResendOTPRequestSerializer
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes   = [BurstRateThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        """Resends OTP to user's verified contact."""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email_or_phone = serializer.validated_data.get('email_or_phone')
            message = OTPService.resend_otp_sync(email_or_phone=email_or_phone)

            logger.info("✅ OTP resent for: %s", email_or_phone)
            return Response({"message": message}, status=status.HTTP_200_OK)

        except drf_serializers.ValidationError as exc:
            logger.warning("⚠️ ResendOTPView validation error: %s", exc)
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            logger.error("❌ ResendOTPView error: %s", str(exc), exc_info=True)
            return Response(
                {"error": "Failed to resend OTP. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ═══════════════════════════════════════════════════════════════════════════
#  GOOGLE AUTH VIEW
# ═══════════════════════════════════════════════════════════════════════════

class GoogleAuthView(generics.CreateAPIView):
    """
    POST /api/v1/auth/google/

    Google OAuth2 sign-in via ID token from the frontend.

    Request Body:
        id_token (str): Google ID token from frontend OAuth2 flow.
        role     (str): 'vendor' or 'client' (for new registrations).

    Success Response 200:
        { "message": "Google Login Successful", "tokens": {...}, "user": {...} }
    """
    serializer_class   = GoogleAuthSerializer
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes   = [BurstRateThrottle]

    def create(self, request, *args, **kwargs) -> Response:
        """Verifies Google ID token and returns JWT access + refresh tokens."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = SyncGoogleAuthService.verify_and_login(
                token=data['id_token'],
                role=data.get('role', 'client'),
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        except ValueError as exc:
            return Response(
                {"status": "error", "message": str(exc), "code": "invalid_google_token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as exc:
            logger.error("❌ GoogleAuthView error: %s", exc, exc_info=True)
            return Response(
                {"status": "error", "message": "Google authentication failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        user       = result['user']
        tokens     = result['tokens']
        is_new     = result['is_new']
        auth_state = _build_auth_response_state(user)

        # ── Create UserSession record on_commit ──────────────────────────
        from rest_framework_simplejwt.tokens import RefreshToken as _RefTok
        from apps.authentication.models import UserSession, LoginEvent
        # CRITICAL FIX: on_commit() MUST be inside explicit atomic() block.
        # In autocommit mode on_commit fires immediately -- not after commit.
        try:
            refresh_obj = _RefTok(tokens['refresh'])
            with transaction.atomic():
                transaction.on_commit(
                    lambda: UserSession.create_from_token(
                        user=user,
                        refresh_token=refresh_obj,
                        request=request,
                    )
                )
                transaction.on_commit(
                    lambda: LoginEvent.record(
                        user=user,
                        ip_address=request.META.get('REMOTE_ADDR', '0.0.0.0'),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        auth_method=LoginEvent.METHOD_GOOGLE,
                        outcome=LoginEvent.OUTCOME_SUCCESS,
                        is_successful=True,
                    )
                )
        except Exception as sess_exc:
            logger.warning("⚠️ GoogleAuthView: session/event record failed: %s", sess_exc)

        logger.info(
            "✅ Google %s: user_id=%s email=%s is_new=%s",
            "register" if is_new else "login",
            user.id, user.email, is_new,
        )

        return Response(
            {
                "status":  "success",
                "message": "Google registration successful." if is_new else "Google login successful.",
                "is_new":  is_new,
                "tokens":  tokens,
                **auth_state,
                "user": {
                    "user_id":    str(user.id),
                    "member_id":  user.member_id,
                    "email":      user.email,
                    "first_name": user.first_name,
                    "last_name":  user.last_name,
                    "role":       user.role,
                    "is_verified": user.is_verified,
                    "is_staff":    user.is_staff,
                    "avatar":     user.avatar,
                },
            },
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )


# ═══════════════════════════════════════════════════════════════════════════
#  REFRESH TOKEN VIEW
# ═══════════════════════════════════════════════════════════════════════════

class RefreshTokenView(generics.GenericAPIView):
    """
    POST /api/v1/auth/token/refresh/

    Refreshes a JWT access token using a valid refresh token.

    Request Body:
        refresh (str): Valid refresh token.

    Success Response 200:
        { "access": "<new access token>" }
    """
    serializer_class   = TokenRefreshSerializer  # Needed for drf-yasg schema
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        """Delegates to SimpleJWT TokenRefreshView with custom renderer."""
        from rest_framework_simplejwt.views import TokenRefreshView
        return TokenRefreshView.as_view()(request._request)


# ═══════════════════════════════════════════════════════════════════════════
#  LOGOUT VIEW
# ═══════════════════════════════════════════════════════════════════════════

class LogoutView(generics.GenericAPIView):
    """
    POST /api/v1/auth/logout/

    Server-side logout — blacklists the refresh token so it cannot be
    reused even if stolen.  Mirrors legacy ``userauths.views.LogoutView``.

    Requires:
        Authorization: Bearer <access_token>
        Body: { "refresh": "<refresh_token>" }

    Success Response 200:
        { "message": "Logout Successful. Your session has been terminated." }

    Error Responses:
        400 — Token already blacklisted or missing
        401 — Not authenticated
    """
    serializer_class   = LogoutSerializer   # Needed for drf-yasg schema
    permission_classes = [IsAuthenticated]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        """Blacklists refresh token, invalidating the server-side session."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError
        from django.db import OperationalError as DbOperationalError

        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required to logout."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                token = RefreshToken(refresh_token)
                token.blacklist()

            logger.info(
                "Logout: refresh token blacklisted — user_id=%s",
                request.user.id,
            )
            return Response(
                {"message": "Logout Successful. Your session has been terminated."},
                status=status.HTTP_200_OK,
            )

        except TokenError as exc:
            logger.warning(
                "LogoutView TokenError user_id=%s: %s",
                getattr(request.user, 'id', 'anon'), str(exc),
            )
            return Response(
                {"error": "Token is already invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except DbOperationalError as exc:
            # Handle DB table lock (can occur under extreme concurrent load on
            # SQLite dev environments; PostgreSQL in production uses row-level
            # locks, so this is an extremely rare edge case in prod).
            logger.warning(
                "LogoutView DB lock on blacklist (concurrent request) user_id=%s: %s",
                getattr(request.user, 'id', 'anon'), str(exc),
            )
            resp = Response(
                {"error": "Server busy. Please retry logout in a moment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
            resp["Retry-After"] = "1"
            return resp

        except Exception as exc:
            logger.error(
                "LogoutView unexpected error: %s", str(exc), exc_info=True
            )
            return Response(
                {"error": "An error occurred during logout. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ═══════════════════════════════════════════════════════════════════════════
#  ME VIEW — Authenticated user profile (for frontend SSR rehydration)
# ═══════════════════════════════════════════════════════════════════════════

class MeView(generics.RetrieveAPIView):
    """
    GET /api/v1/auth/me/

    Returns the authenticated user's full profile.

    Used by the frontend useAuthHydration() hook to rehydrate Zustand
    user state on page refresh — without requiring a full re-login.

    Authorization: Bearer <access_token>

    Success Response 200:
        {
          "id":          "<uuid>",
          "member_id":   "<member_id>",
          "email":       "user@example.com",
          "phone":       null,
          "first_name":  "John",
          "last_name":   "Doe",
          "role":        "client",
          "is_verified": true,
          "is_staff":    false,
          "avatar":      null,
          "date_joined": "2026-01-15T10:00:00Z"
        }

    Error Responses:
        401 — Not authenticated / token expired
    """
    permission_classes = [IsAuthenticated]
    renderer_classes   = [CustomJSONRenderer]

    def get(self, request, *args, **kwargs) -> Response:
        """Returns the requesting user's profile from the JWT token claim."""
        user = request.user
        return Response(
            {
                "id":          str(user.id),
                "member_id":   user.member_id,
                "email":       user.email,
                "phone":       str(user.phone) if user.phone else None,
                "first_name":  user.first_name,
                "last_name":   user.last_name,
                "role":        user.role,
                "is_verified": user.is_verified,
                "is_staff":    user.is_staff,
                "avatar":      user.avatar,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            },
            status=status.HTTP_200_OK,
        )

