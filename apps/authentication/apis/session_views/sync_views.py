# apps/authentication/apis/session_views/sync_views.py
"""
Session Management Views — Telegram-style Active Sessions Dashboard
===================================================================

Endpoints:
  GET  /api/v1/auth/sessions/                   — list all active sessions for current user
  DELETE /api/v1/auth/sessions/<id>/             — terminate a specific session (logout from device)
  POST   /api/v1/auth/sessions/revoke-others/    — logout all other devices, keep current
  GET  /api/v1/auth/login-events/                — list last 10 login events (security audit trail)

All endpoints require IsVerifiedUser (authenticated + active + OTP-verified).
"""
import logging
from drf_spectacular.utils import extend_schema
from django.db import transaction
from rest_framework import generics, status
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVerifiedUser
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.authentication.selectors import get_active_sessions, get_login_events
from apps.authentication.serializers import (
    UserSessionSerializer,
    LoginEventSerializer,
)

logger = logging.getLogger("application")


def _get_current_jti(request) -> str | None:
    """Extract the JTI claim from the current request's JWT access token."""
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication

        auth = JWTAuthentication()
        # Handle cases where get_header might be missing or fail
        header = auth.get_header(request) if hasattr(auth, 'get_header') else None
        if not header:
            header_val = request.headers.get("Authorization", "").split()
            if len(header_val) == 2:
                header = header_val[1]
        
        validated_token = auth.get_validated_token(header)
        return str(validated_token.get("jti", ""))
    except Exception:
        return None


# ===========================================================================
# GET  /api/v1/auth/sessions/
# ===========================================================================


class SessionListView(generics.ListAPIView):
    """
    List all active sessions (devices) for the authenticated user.

    Useful for the Security Dashboard "Active Sessions" section.
    Allows users to see which devices are currently logged in.

    Uses get_active_sessions() selector for optimized DB query with select_related.
    """
    serializer_class = UserSessionSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        """Return active sessions for the user."""
        return get_active_sessions(user=self.request.user, limit=20)

    @extend_schema(
        summary="List active sessions",
        description="Returns a list of all devices/browsers currently logged into this account.",
        responses={200: UserSessionSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """List sessions with standardized success response."""
        queryset = self.get_queryset()
        current_jti = _get_current_jti(request)
        
        serializer = self.get_serializer(
            queryset,
            many=True,
            context={"current_jti": current_jti, "request": request},
        )
        return success_response(
            data={
                "count": len(serializer.data),
                "sessions": serializer.data,
            },
            message="Active sessions retrieved successfully."
        )


# ===========================================================================
# DELETE /api/v1/auth/sessions/<str:session_id>/
# ===========================================================================


class SessionRevokeView(generics.DestroyAPIView):
    """
    Revoke (terminate) a specific session by UUID7 string ID.

    Security:
      - Only the session owner can revoke their own sessions (user FK enforced).
      - The underlying refresh token JTI is blacklisted via SimpleJWT.
      - The UserSession row is deleted atomically in the same transaction.
    """
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    lookup_url_kwarg = 'session_id'

    def get_queryset(self):
        """Restrict deletion to user's own sessions."""
        from apps.authentication.models import UserSession
        return UserSession.objects.filter(user=self.request.user)

    @extend_schema(
        summary="Revoke session",
        description="Terminates a specific session, logging out the corresponding device.",
        responses={200: None, 404: None}
    )
    def destroy(self, request, *args, **kwargs):
        """
        Revoke a session by its UUID7 primary key (string).

        All models inherit from CommonTimestampModel which uses UUID7 as PK.
        The URL parameter is <str:session_id> — NOT <int:session_id>.
        """
        from apps.authentication.models import UserSession
        session_id = self.kwargs.get(self.lookup_url_kwarg)

        try:
            with transaction.atomic():
                # ── select_for_update(): Acquires a row-level DB lock ──────────────
                # Prevents concurrent DELETE on the same session from two simultaneous
                # requests (e.g. user double-clicking "Revoke" or retry storms at
                # 100k RPS). The second request will block until the first completes,
                # then see DoesNotExist → return 404 correctly.
                try:
                    session = UserSession.objects.select_for_update(nowait=False).get(
                        pk=session_id, user=request.user
                    )
                except UserSession.DoesNotExist:
                    return error_response(
                        message="Session not found or already terminated.",
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except (ValueError, Exception) as e:
                    # Invalid UUID format — treat as not found rather than leaking DB error details.
                    logger.debug("SessionRevokeView: invalid session_id format '%s': %s", session_id, e)
                    return error_response(
                        message="Session not found.",
                        status=status.HTTP_404_NOT_FOUND,
                    )

                jti = session.jti

                # Blacklist via SimpleJWT for immediate invalidation
                try:
                    from rest_framework_simplejwt.token_blacklist.models import (
                        OutstandingToken,
                        BlacklistedToken,
                    )
                    outstanding = OutstandingToken.objects.filter(jti=jti).first()
                    if outstanding:
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                        logger.info(
                            "🔒 Session %s blacklisted (JTI=%s) for user=%s",
                            session_id, jti, request.user.pk,
                        )
                except Exception as bl_exc:
                    logger.warning("⚠️ Could not blacklist JTI=%s for session=%s: %s", jti, session_id, bl_exc)

                session.delete()

        except Exception as exc:
            logger.error("SessionRevokeView.destroy failed: %s", exc, exc_info=True)
            return error_response(
                message="Failed to revoke session. Please try again.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info("✅ Session %s revoked for user=%s", session_id, request.user.pk)
        return success_response(message="Session revoked successfully.")


# ===========================================================================
# POST /api/v1/auth/sessions/revoke-others/
# ===========================================================================


class SessionRevokeOthersView(generics.GenericAPIView):
    """
    Logout all other devices — keeps only the current session.

    Useful when a user suspects their account is compromised on another device.
    All other sessions except the current request's session are blacklisted
    and deleted in a single atomic transaction.

    Returns the count of sessions terminated.
    """
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @extend_schema(
        summary="Revoke all other sessions",
        description="Terminates all active sessions for this account except for the current one.",
        responses={200: None}
    )
    def post(self, request, *args, **kwargs):
        """Terminates other sessions in a transaction."""
        from apps.authentication.models import UserSession
        current_jti = _get_current_jti(request)

        # All sessions except the one that matches the current token
        other_sessions = UserSession.objects.filter(user=request.user)
        if current_jti:
            other_sessions = other_sessions.exclude(jti=current_jti)

        revoked_count = 0
        with transaction.atomic():
            for session in other_sessions:
                try:
                    from rest_framework_simplejwt.token_blacklist.models import (
                        OutstandingToken,
                        BlacklistedToken,
                    )
                    outstanding = OutstandingToken.objects.filter(jti=session.jti).first()
                    if outstanding:
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                except Exception as bl_exc:
                    logger.warning("⚠️ Could not blacklist JTI=%s: %s", session.jti, bl_exc)
                revoked_count += 1
            other_sessions.delete()

        logger.info(
            "✅ RevokeOthers: %d sessions terminated for user=%s",
            revoked_count, request.user.pk,
        )
        return success_response(
            data={"terminated_count": revoked_count},
            message=f"{revoked_count} other session(s) terminated successfully."
        )


# ===========================================================================
# GET  /api/v1/auth/login-events/
# ===========================================================================


class LoginEventListView(generics.ListAPIView):
    """
    Return the last 10 login events (attempts) for the authenticated user.

    Useful for the Security Dashboard "Recent Login Activity" section.
    Analogous to Binance's "Login Activity" and Google's "Recent Security Events".

    Uses LoginEventSerializer for validated, Swagger-documented responses.
    Uses get_login_events() selector for optimized ORM query with select_related.
    """
    serializer_class = LoginEventSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        """Return recent login events."""
        return get_login_events(user=self.request.user, limit=10)

    @extend_schema(
        summary="List login events",
        description="Returns a security audit trail of recent login attempts (successful or failed).",
        responses={200: LoginEventSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """List events with standardized success response."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data={
                "count": len(serializer.data),
                "events": serializer.data,
            },
            message="Login history retrieved successfully."
        )

# apps/authentication/apis/session_views/sync_views.py
"""
Session Management Views — Telegram-style Active Sessions Dashboard
===================================================================

Endpoints:
  GET  /api/v1/auth/sessions/                   — list all active sessions for current user
  DELETE /api/v1/auth/sessions/<id>/             — terminate a specific session (logout from device)
  POST   /api/v1/auth/sessions/revoke-others/    — logout all other devices, keep current
  GET  /api/v1/auth/login-events/                — list last 10 login events (security audit trail)

All endpoints require IsVerifiedUser (authenticated + active + OTP-verified).

Architecture:
  - Views delegate all DB reads to selectors (session_selector.py)
  - Serializers (session.py) replace inline raw-dict serialization
  - Transaction.atomic() wraps all writes
"""

import logging
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsVerifiedUser
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.selectors import get_active_sessions, get_login_events
from apps.authentication.serializers import (
    UserSessionSerializer,
    LoginEventSerializer,
)

logger = logging.getLogger("application")


def _get_current_jti(request) -> str | None:
    """Extract the JTI claim from the current request's JWT access token."""
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication

        auth = JWTAuthentication()
        validated_token = auth.get_validated_token(
            auth.get_raw_token(auth.get_header(request))
        )
        return str(validated_token.get("jti", ""))
    except Exception:
        return None


# ===========================================================================
# GET /api/v1/auth/sessions/
# ===========================================================================


class SessionListView(APIView):
    """
    List all active sessions for the authenticated user.

    Returns the 20 most recent sessions, sorted by last_used_at descending.
    Each session includes device, location, and is_current flag.

    The ``is_current`` field marks the session being used for this request,
    allowing the frontend to highlight it (styled differently, no revoke button).
    """

    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        current_jti = _get_current_jti(request)

        # Use selector for optimized DB query with select_related
        sessions = get_active_sessions(user=request.user, limit=20)

        serializer = UserSessionSerializer(
            sessions,
            many=True,
            context={"current_jti": current_jti, "request": request},
        )

        return Response(
            {
                "status": "success",
                "count": len(serializer.data),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# DELETE /api/v1/auth/sessions/<str:session_id>/
# ===========================================================================


class SessionRevokeView(APIView):
    """
    Revoke (terminate) a specific session by UUID7 string ID.

    Security:
      - Only the session owner can revoke their own sessions (user FK enforced).
      - The underlying refresh token JTI is blacklisted via SimpleJWT.
      - The UserSession row is deleted atomically in the same transaction.
    """

    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def delete(self, request, session_id: str):
        """
        Revoke a session by its UUID7 primary key (string).

        All models inherit from CommonTimestampModel which uses UUID7 as PK.
        The URL parameter is <str:session_id> — NOT <int:session_id>.
        """
        from apps.authentication.models import UserSession

        try:
            with transaction.atomic():
                # ── select_for_update(): Acquires a row-level DB lock ──────────────
                # Prevents concurrent DELETE on the same session from two simultaneous
                # requests (e.g. user double-clicking "Revoke" or retry storms at
                # 100k RPS). The second request will block until the first completes,
                # then see DoesNotExist → return 404 correctly.
                try:
                    session = UserSession.objects.select_for_update(nowait=False).get(
                        pk=session_id, user=request.user
                    )
                except UserSession.DoesNotExist:
                    return Response(
                        {"status": "error", "message": "Session not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except (ValueError, Exception) as e:
                    # Invalid UUID format (e.g. '999999' instead of a UUID7) —
                    # treat as not found rather than leaking DB error details.
                    logger.debug(
                        "SessionRevokeView: invalid session_id format '%s': %s",
                        session_id,
                        e,
                    )
                    return Response(
                        {"status": "error", "message": "Session not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                jti = session.jti

                # Blacklist the refresh token so it can't be refreshed again
                try:
                    from rest_framework_simplejwt.token_blacklist.models import (
                        OutstandingToken,
                        BlacklistedToken,
                    )

                    outstanding = OutstandingToken.objects.filter(jti=jti).first()
                    if outstanding:
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                        logger.info(
                            "🔒 Session %s blacklisted (JTI=%s) for user=%s",
                            session_id,
                            jti,
                            request.user.pk,
                        )
                except Exception as bl_exc:
                    logger.warning(
                        "⚠️ Could not blacklist JTI=%s for session=%s: %s",
                        jti,
                        session_id,
                        bl_exc,
                    )

                session.delete()

        except Exception as exc:
            logger.error("SessionRevokeView.delete failed: %s", exc, exc_info=True)
            raise

        logger.info("✅ Session %s revoked for user=%s", session_id, request.user.pk)
        return Response(
            {"status": "success", "message": "Session revoked successfully."},
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# POST /api/v1/auth/sessions/revoke-others/
# ===========================================================================


class SessionRevokeOthersView(APIView):
    """
    Logout all other devices — keeps only the current session.

    Useful when a user suspects their account is compromised on another device.
    All other sessions except the current request's session are blacklisted
    and deleted in a single atomic transaction.

    Returns the count of sessions terminated.
    """

    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        from apps.authentication.models import UserSession

        current_jti = _get_current_jti(request)

        # All sessions except the one that matches the current token
        other_sessions = UserSession.objects.filter(user=request.user)
        if current_jti:
            other_sessions = other_sessions.exclude(jti=current_jti)

        revoked_count = 0

        with transaction.atomic():
            for session in other_sessions:
                try:
                    from rest_framework_simplejwt.token_blacklist.models import (
                        OutstandingToken,
                        BlacklistedToken,
                    )

                    outstanding = OutstandingToken.objects.filter(
                        jti=session.jti
                    ).first()
                    if outstanding:
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                except Exception as bl_exc:
                    logger.warning(
                        "⚠️ Could not blacklist JTI=%s: %s", session.jti, bl_exc
                    )
                revoked_count += 1

            other_sessions.delete()

        logger.info(
            "✅ RevokeOthers: %d sessions terminated for user=%s",
            revoked_count,
            request.user.pk,
        )
        return Response(
            {
                "status": "success",
                "message": f"{revoked_count} other session(s) terminated.",
                "terminated_count": revoked_count,
            },
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# GET  /api/v1/auth/login-events/
# ===========================================================================


class LoginEventListView(APIView):
    """
    Return the last 10 login events (attempts) for the authenticated user.

    Useful for the Security Dashboard "Recent Login Activity" section.
    Analogous to Binance's "Login Activity" and Google's "Recent Security Events".

    Uses LoginEventSerializer for validated, Swagger-documented responses.
    Uses get_login_events() selector for optimized ORM query with select_related.
    """

    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        # Use selector for optimized DB query
        events = get_login_events(user=request.user, limit=10)

        serializer = LoginEventSerializer(
            events,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "status": "success",
                "count": len(serializer.data),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
    Logout all other devices — keeps only the current session.

    Useful when a user suspects their account is compromised on another device.
    All other sessions except the current request's session are blacklisted
    and deleted in a single atomic transaction.

    Returns the count of sessions terminated.
    """
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @extend_schema(
        summary="Revoke all other sessions",
        description="Terminates all active sessions for this account except for the current one.",
        responses={200: None}
    )
    def post(self, request, *args, **kwargs):
        """Terminates other sessions in a transaction."""
        from apps.authentication.models import UserSession
        current_jti = _get_current_jti(request)

        # All sessions except the one that matches the current token
        other_sessions = UserSession.objects.filter(user=request.user)
        if current_jti:
            other_sessions = other_sessions.exclude(jti=current_jti)

        revoked_count = 0
        with transaction.atomic():
            for session in other_sessions:
                try:
                    from rest_framework_simplejwt.token_blacklist.models import (
                        OutstandingToken,
                        BlacklistedToken,
                    )
                    outstanding = OutstandingToken.objects.filter(jti=session.jti).first()
                    if outstanding:
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                except Exception as bl_exc:
                    logger.warning("⚠️ Could not blacklist JTI=%s: %s", session.jti, bl_exc)
                revoked_count += 1
            other_sessions.delete()

        logger.info(
            "✅ RevokeOthers: %d sessions terminated for user=%s",
            revoked_count, request.user.pk,
        )
        return success_response(
            data={"terminated_count": revoked_count},
            message=f"{revoked_count} other session(s) terminated successfully."
        )


# ===========================================================================
# GET  /api/v1/auth/login-events/
# ===========================================================================


class LoginEventListView(generics.ListAPIView):
    """
    Return the last 10 login events (attempts) for the authenticated user.

    Useful for the Security Dashboard "Recent Login Activity" section.
    Analogous to Binance's "Login Activity" and Google's "Recent Security Events".

    Uses LoginEventSerializer for validated, Swagger-documented responses.
    Uses get_login_events() selector for optimized ORM query with select_related.
    """
    serializer_class = LoginEventSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        """Return recent login events."""
        return get_login_events(user=self.request.user, limit=10)

    @extend_schema(
        summary="List login events",
        description="Returns a security audit trail of recent login attempts (successful or failed).",
        responses={200: LoginEventSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """List events with standardized success response."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data={
                "count": len(serializer.data),
                "events": serializer.data,
            },
            message="Login history retrieved successfully."
        )

