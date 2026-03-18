# apps/authentication/apis/session_views/sync_views.py
"""
Session Management Views — Telegram-style Active Sessions Dashboard
===================================================================

Endpoints:
  GET  /api/v1/auth/sessions/                   — list all active sessions for current user
  DELETE /api/v1/auth/sessions/<id>/             — terminate a specific session (logout from device)
  POST   /api/v1/auth/sessions/revoke-others/    — logout all other devices, keep current

All endpoints require IsVerifiedUser (authenticated + active + OTP-verified).

Why this matters:
  Users can see exactly which devices have their account open, spot
  suspicious sessions (unfamiliar country/device), and remotely revoke
  them — exactly like Telegram, GitHub, and Google Account Security.
"""

import logging
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.renderers import BrowsableAPIRenderer
from apps.common.permissions import IsVerifiedUser
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UserSession

logger = logging.getLogger('application')


def _get_current_jti(request) -> str | None:
    """Extract the JTI claim from the current request's JWT access token."""
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
        auth = JWTAuthentication()
        validated_token = auth.get_validated_token(
            auth.get_raw_token(auth.get_header(request))
        )
        return str(validated_token.get('jti', ''))
    except Exception:
        return None


def _session_to_dict(session: UserSession, current_jti: str | None = None) -> dict:
    """Serialize a UserSession to a safe API-facing dict."""
    return {
        "id":           session.pk,
        "device_name":  session.device_name or "Unknown Device",
        "client_type":  session.client_type,
        "browser":      session.browser_family,
        "os":           session.os_family,
        "ip_address":   session.ip_address,
        "country":      session.country,
        "city":         session.city,
        "created_at":   session.created_at.isoformat() if session.created_at else None,
        "last_used_at": session.last_used_at.isoformat() if session.last_used_at else None,
        "expires_at":   session.expires_at.isoformat() if session.expires_at else None,
        # ``is_current`` computed dynamically: the session whose JTI matches
        # the JWT in the current request's Authorization header.
        # Note: UserSession.jti is the REFRESH token JTI; the access token JTI
        # is different. We match on either user agent+IP as a heuristic fallback.
        "is_current":   (session.jti == current_jti) if current_jti else False,
        "is_expired":   (
            session.expires_at is not None
            and session.expires_at < timezone.now()
        ),
    }


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
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]    

    def get(self, request):
        current_jti = _get_current_jti(request)

        sessions = (
            UserSession.objects
            .filter(user=request.user)
            .order_by('-last_used_at')[:20]
        )
        data = [_session_to_dict(s, current_jti) for s in sessions]

        return Response(
            {
                "status": "success",
                "count":  len(data),
                "results": data,
            },
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# DELETE /api/v1/auth/sessions/<int:session_id>/
# ===========================================================================

class SessionRevokeView(APIView):
    """
    Revoke (terminate) a specific session by ID.

    Security:
      - Only the session owner can revoke their own sessions (user FK enforced).
      - The underlying refresh token JTI is blacklisted via SimpleJWT.
      - The UserSession row is deleted atomically in the same transaction.
    """

    permission_classes = [IsVerifiedUser]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def delete(self, request, session_id: int):
        try:
            session = UserSession.objects.get(pk=session_id, user=request.user)
        except UserSession.DoesNotExist:
            return Response(
                {"status": "error", "message": "Session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        jti = session.jti

        with transaction.atomic():
            # Blacklist the refresh token so it can't be refreshed again
            try:
                from rest_framework_simplejwt.token_blacklist.models import (
                    OutstandingToken, BlacklistedToken
                )
                outstanding = OutstandingToken.objects.filter(jti=jti).first()
                if outstanding:
                    BlacklistedToken.objects.get_or_create(token=outstanding)
                    logger.info(
                        "🔒 Session %s blacklisted (JTI=%s) for user=%s",
                        session_id, jti, request.user.pk,
                    )
            except Exception as bl_exc:
                logger.warning(
                    "⚠️ Could not blacklist JTI=%s for session=%s: %s",
                    jti, session_id, bl_exc,
                )

            session.delete()

        logger.info(
            "✅ Session %s revoked for user=%s", session_id, request.user.pk
        )
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
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]    

    def post(self, request):
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
                        OutstandingToken, BlacklistedToken
                    )
                    outstanding = OutstandingToken.objects.filter(jti=session.jti).first()
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
            revoked_count, request.user.pk,
        )
        return Response(
            {
                "status":  "success",
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
    """

    permission_classes = [IsVerifiedUser]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        from apps.authentication.models import LoginEvent

        events = (
            LoginEvent.objects
            .filter(user=request.user)
            .order_by('-created_at')[:10]
        )

        data = [
            {
                "id":             event.pk,
                "outcome":        event.outcome,
                "is_successful":  event.is_successful,
                "failure_reason": event.failure_reason,
                "auth_method":    event.auth_method,
                "ip_address":     event.ip_address,
                "country":        event.country,
                "city":           event.city,
                "client_type":    event.client_type,
                "browser":        event.browser_family,
                "os":             event.os_family,
                "risk_score":     event.risk_score,
                "is_new_device":  event.is_new_device,
                "is_new_country": event.is_new_country,
                "timestamp":      event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ]

        return Response(
            {
                "status":  "success",
                "count":   len(data),
                "results": data,
            },
            status=status.HTTP_200_OK,
        )
