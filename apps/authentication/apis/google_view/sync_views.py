# apps/authentication/apis/google_view/sync_views.py
"""
Google Authentication Views — Synchronous DRF (WSGI)
===================================================

Endpoints for Google OAuth2 authentication.
Verifies Google ID tokens and handles the find-or-create user lifecycle.
"""

import logging
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.authentication.serializers import GoogleAuthSerializer
from apps.authentication.services.google_service import SyncGoogleAuthService
from apps.authentication.services.profile_service.profile_service import get_post_auth_state
from apps.authentication.throttles import BurstRateThrottle
from apps.client.tasks import provision_client_defaults
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


# ===========================================================================
# POST /api/v1/auth/google/
# ===========================================================================


class GoogleAuthView(generics.CreateAPIView):
    """
    Authenticate a user via Google OAuth2 ID Token.

    Flow:
      1. Verify the provided 'id_token' with Google's public keys.
      2. Identify or register the user based on email (is_new flag returned).
      3. Provision defaults for new client users asynchronously.
      4. Record UserSession and LoginEvent for audit tracking.
      5. Issue JWT tokens and profile state for frontend routing.

    Status Codes:
      - 201 Created: New user registered.
      - 200 OK: Returning user logged in.
      - 401 Unauthorized: Invalid or expired token.
    """
    serializer_class = GoogleAuthSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_classes = [BurstRateThrottle]

    def create(self, request, *args, **kwargs) -> Response:
        """Verifies Google ID token and returns JWT access + refresh tokens."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = SyncGoogleAuthService.verify_and_login(
                token=data["id_token"],
                role=data.get("role", "client"),
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ValueError as exc:
            logger.warning("⚠️ GoogleAuthView: invalid token — %s", exc)
            return error_response(
                message="Invalid or expired Google token. Please try signing in again.",
                code="invalid_google_token",
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as exc:
            logger.error("❌ GoogleAuthView unexpected error: %s", exc, exc_info=True)
            return error_response(
                message="Google authentication failed. Please try again.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        user = result["user"]
        tokens = result["tokens"]
        is_new = result["is_new"]
        auth_state = get_post_auth_state(user=user)

        # ── Register UserSession + LoginEvent on_commit ─────────────────────
        from rest_framework_simplejwt.tokens import RefreshToken as _RefTok
        from apps.authentication.models import UserSession, LoginEvent

        try:
            refresh_obj = _RefTok(tokens["refresh"])
            with transaction.atomic():
                if is_new and user.role == "client":
                    transaction.on_commit(
                        lambda: provision_client_defaults.delay(str(user.pk))
                    )
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
                        ip_address=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                        user_agent=request.META.get("HTTP_USER_AGENT", ""),
                        auth_method=LoginEvent.METHOD_GOOGLE,
                        outcome=LoginEvent.OUTCOME_SUCCESS,
                        is_successful=True,
                    )
                )
        except Exception as sess_exc:
            logger.warning("⚠️ GoogleAuthView: session/event record failed: %s", sess_exc)

        # ── Differentiated logging for register vs login ─────────────────────
        if is_new:
            logger.info("🆕 Google REGISTER: user_id=%s email=%s role=%s", user.id, user.email, user.role)
        else:
            logger.info("✅ Google LOGIN: user_id=%s email=%s", user.id, user.email)

        # Human-readable message for AuthAlert pop-up display
        msg = (
            "Welcome to FASHIONISTAR! Your account has been created via Google."
            if is_new
            else "Welcome back! Google sign-in successful."
        )

        return success_response(
            data={
                "is_new": is_new,
                "redirect": (
                    f'{auth_state["dashboard_entrypoint"]}?welcome=true'
                    if is_new
                    else auth_state["dashboard_entrypoint"]
                ),
                "tokens": {
                    "access": str(tokens["access"]),
                    "refresh": str(tokens["refresh"]),
                },
                "access": str(tokens["access"]),
                "refresh": str(tokens["refresh"]),
                **auth_state,
                "user": {
                    "user_id": str(user.id),
                    "member_id": user.member_id,
                    "email": user.email if user.email else None,
                    "phone": str(user.phone) if user.phone else "",
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "role": user.role,
                    "is_verified": user.is_verified,
                    "is_staff": user.is_staff,
                    "avatar": (
                        str(user.avatar.url)
                        if hasattr(user.avatar, "url") and user.avatar
                        else None
                    ),
                    "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                },
            },
            message=msg,
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )

