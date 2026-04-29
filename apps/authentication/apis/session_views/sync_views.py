# apps/authentication/apis/session_views/sync_views.py
"""
Session Management Views — Security Dashboard DRF Endpoints
===========================================================

Endpoints:
  GET    /api/v1/auth/sessions/                → list active sessions
  DELETE /api/v1/auth/sessions/<session_id>/   → revoke one session
  POST   /api/v1/auth/sessions/revoke-others/  → revoke all other sessions
  GET    /api/v1/auth/login-events/            → list recent login events

All write paths remain synchronous and transaction-protected. Revocation marks
rows as revoked instead of deleting them so the platform keeps a durable audit
trail for session lifecycle events.
"""

from __future__ import annotations

import logging

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.renderers import BrowsableAPIRenderer

from apps.authentication.selectors import get_active_sessions, get_login_events
from apps.authentication.serializers import LoginEventSerializer, UserSessionSerializer
from apps.common.permissions import IsVerifiedUser
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger("application")


def _get_current_jti(request) -> str | None:
    """Extract the JTI claim from the current JWT access token."""

    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication

        auth = JWTAuthentication()
        header = auth.get_header(request) if hasattr(auth, "get_header") else None
        if not header:
            header_parts = request.headers.get("Authorization", "").split()
            if len(header_parts) == 2:
                header = header_parts[1]

        validated_token = auth.get_validated_token(header)
        return str(validated_token.get("jti", ""))
    except Exception:
        return None


def _blacklist_refresh_jti(jti: str) -> None:
    """Blacklist an outstanding refresh token JTI when present."""

    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        outstanding = OutstandingToken.objects.filter(jti=jti).first()
        if outstanding:
            BlacklistedToken.objects.get_or_create(token=outstanding)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not blacklist refresh JTI=%s: %s", jti, exc)


class SessionListView(generics.ListAPIView):
    """List active sessions for the authenticated user."""

    serializer_class = UserSessionSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        """Return the latest active sessions for the requesting user."""

        return get_active_sessions(user=self.request.user, limit=20)

    @extend_schema(
        summary="List active sessions",
        description=(
            "Returns a list of active devices and browsers currently signed in "
            "to this account."
        ),
        responses={200: UserSessionSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """Serialize the active session registry with a stable response envelope."""

        queryset = self.get_queryset()
        current_jti = _get_current_jti(request)
        serializer = self.get_serializer(
            queryset,
            many=True,
            context={"current_jti": current_jti, "request": request},
        )
        return success_response(
            data={"count": len(serializer.data), "sessions": serializer.data},
            message="Active sessions retrieved successfully.",
        )


class SessionRevokeView(generics.DestroyAPIView):
    """Revoke a specific active session owned by the authenticated user."""

    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_url_kwarg = "session_id"

    def get_queryset(self):
        """Restrict revocation to the caller's active sessions."""

        from apps.authentication.models import UserSession

        return UserSession.objects.filter(user=self.request.user)

    @extend_schema(
        summary="Revoke one session",
        description="Terminates a specific session and blacklists its refresh token.",
        responses={200: None, 404: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Revoke a single session inside an atomic write boundary."""

        from apps.authentication.models import UserSession

        session_id = self.kwargs.get(self.lookup_url_kwarg)
        try:
            with transaction.atomic():
                try:
                    session = (
                        UserSession.objects.select_for_update()
                        .get(pk=session_id, user=request.user)
                    )
                except UserSession.DoesNotExist:
                    return error_response(
                        message="Session not found or already terminated.",
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except (TypeError, ValueError):
                    return error_response(
                        message="Session not found.",
                        status=status.HTTP_404_NOT_FOUND,
                    )

                _blacklist_refresh_jti(session.jti)
                if not session.revoke(reason="user_revoked_session"):
                    return error_response(
                        message="Session not found or already terminated.",
                        status=status.HTTP_404_NOT_FOUND,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.error("SessionRevokeView.destroy failed: %s", exc, exc_info=True)
            return error_response(
                message="Failed to revoke session. Please try again.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info("Session %s revoked for user=%s", session_id, request.user.pk)
        return success_response(message="Session revoked successfully.")


class SessionRevokeOthersView(generics.GenericAPIView):
    """Revoke every other active session for the authenticated user."""

    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @extend_schema(
        summary="Revoke all other sessions",
        description=(
            "Terminates every active session on the account except the current "
            "request's session."
        ),
        responses={200: None},
    )
    def post(self, request, *args, **kwargs):
        """Revoke all other sessions within one atomic transaction."""

        from apps.authentication.models import UserSession

        current_jti = _get_current_jti(request)
        other_sessions = UserSession.objects.filter(user=request.user)
        if current_jti:
            other_sessions = other_sessions.exclude(jti=current_jti)

        revoked_count = 0
        try:
            with transaction.atomic():
                sessions_to_revoke = list(other_sessions.select_for_update())
                for session in sessions_to_revoke:
                    _blacklist_refresh_jti(session.jti)
                    if session.revoke(reason="user_revoked_other_session"):
                        revoked_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "SessionRevokeOthersView.post failed for user=%s: %s",
                request.user.pk,
                exc,
                exc_info=True,
            )
            return error_response(
                message="Failed to revoke the other sessions. Please try again.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "RevokeOthers completed for user=%s terminated=%s",
            request.user.pk,
            revoked_count,
        )
        return success_response(
            data={"terminated_count": revoked_count},
            message=f"{revoked_count} other session(s) terminated successfully.",
        )


class LoginEventListView(generics.ListAPIView):
    """Return recent login-event audit entries for the authenticated user."""

    serializer_class = LoginEventSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        """Return recent login events for the authenticated user."""

        return get_login_events(user=self.request.user, limit=10)

    @extend_schema(
        summary="List login events",
        description="Returns a recent security audit trail of login attempts.",
        responses={200: LoginEventSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """Serialize login history with a consistent response envelope."""

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data={"count": len(serializer.data), "events": serializer.data},
            message="Login history retrieved successfully.",
        )
