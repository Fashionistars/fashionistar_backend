# apps/authentication/apis/google_view/sync_views.py
"""
Google Auth View — Synchronous DRF (WSGI)
==========================================

POST /api/v1/auth/google/

Verifies a Google ID-token from the Next.js frontend, finds-or-creates
the user via SyncGoogleAuthService, and returns JWT tokens.

Differentiates NEW USER REGISTRATION (is_new=True → 201 Created) from
RETURNING USER LOGIN (is_new=False → 200 OK) in:
  - HTTP status code  (201 vs 200)
  - Response message  (distinct human-readable strings)
  - Log message       ("Google REGISTER" vs "Google LOGIN")
  - redirect hint     (/dashboard?welcome=true vs /dashboard)

This allows AuthAlert to show different success banners and the frontend
router to redirect to the correct post-login page.
"""

import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.authentication.serializers import GoogleAuthSerializer
from apps.authentication.services.google_service import SyncGoogleAuthService
from apps.authentication.throttles import BurstRateThrottle
from apps.common.renderers import CustomJSONRenderer

logger = logging.getLogger(__name__)


class GoogleAuthView(generics.CreateAPIView):
    """
    POST /api/v1/auth/google/

    Google OAuth2 sign-in via ID token from the frontend.

    Request Body:
        id_token (str): Google ID token from frontend OAuth2 flow.
        role     (str): 'vendor' or 'client' (for new registrations).

    Success 201 (NEW USER):
        { "status": "success", "message": "Welcome...", "is_new": true, "tokens": {...}, "redirect": "/dashboard?welcome=true" }

    Success 200 (EXISTING USER):
        { "status": "success", "message": "Welcome back...", "is_new": false, "tokens": {...}, "redirect": "/dashboard" }

    Error 401 — Invalid or expired Google token.
    Error 500 — Unexpected server error.
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
            return Response(
                {
                    "status": "error",
                    "message": "Invalid or expired Google token. Please try signing in again.",
                    "code": "invalid_google_token",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as exc:
            logger.error("❌ GoogleAuthView unexpected error: %s", exc, exc_info=True)
            return Response(
                {
                    "status": "error",
                    "message": "Google authentication failed. Please try again.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        user = result["user"]
        tokens = result["tokens"]
        is_new = result["is_new"]

        # ── Register UserSession + LoginEvent on_commit ─────────────────────
        # CRITICAL: on_commit() MUST be inside explicit atomic() block.
        # In autocommit mode on_commit fires immediately without rollback guard.
        from rest_framework_simplejwt.tokens import RefreshToken as _RefTok
        from apps.authentication.models import UserSession, LoginEvent

        try:
            refresh_obj = _RefTok(tokens["refresh"])
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
                        ip_address=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                        user_agent=request.META.get("HTTP_USER_AGENT", ""),
                        auth_method=LoginEvent.METHOD_GOOGLE,
                        outcome=LoginEvent.OUTCOME_SUCCESS,
                        is_successful=True,
                    )
                )
        except Exception as sess_exc:
            logger.warning(
                "⚠️ GoogleAuthView: session/event record failed: %s", sess_exc
            )

        # ── Differentiated logging for register vs login ─────────────────────
        if is_new:
            logger.info(
                "🆕 Google REGISTER: user_id=%s email=%s role=%s",
                user.id,
                user.email,
                user.role,
            )
        else:
            logger.info(
                "✅ Google LOGIN: user_id=%s email=%s",
                user.id,
                user.email,
            )

        return Response(
            {
                "status": "success",
                # Human-readable message for AuthAlert pop-up display
                "message": (
                    "Welcome to FASHIONISTAR! Your account has been created via Google."
                    if is_new
                    else "Welcome back! Google sign-in successful."
                ),
                # Frontend differentiator: show onboarding for new, dashboard for returning
                "is_new": is_new,
                "redirect": "/dashboard?welcome=true" if is_new else "/dashboard",
                "tokens": {
                    "access": str(tokens["access"]),
                    "refresh": str(tokens["refresh"]),
                },
                # ── Flat top-level tokens for LoginResponseSchema.transform() ──
                # The schema merges tokens.access/refresh to top-level access/refresh
                # when tokens block is present. This ensures Zustand store
                # always receives access + refresh regardless of response shape.
                "user": {
                    # ✅ KEY FIX: 'id' not 'user_id' — matches Zod user.id (required)
                    "id":            str(user.id),
                    "member_id":     user.member_id,
                    "email":         user.email if user.email else None,
                    # ✅ KEY FIX: omit phone if null/empty — Zod z.string().optional()
                    # accepts undefined but rejects null. Set to empty string if no phone.
                    "phone":         str(user.phone) if user.phone else "",
                    "first_name":    user.first_name or "",
                    "last_name":     user.last_name or "",
                    "role":          user.role,
                    "is_verified":   user.is_verified,
                    "is_staff":      user.is_staff,
                    "avatar":        (
                        str(user.avatar.url) if hasattr(user.avatar, 'url') and user.avatar
                        else None
                    ),
                    "date_joined":   (
                        user.date_joined.isoformat() if user.date_joined else None
                    ),
                },
            },
            # 201 Created for new registration, 200 OK for returning login
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )
