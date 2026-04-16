# apps/authentication/apis/password_views/sync_views.py
"""
Synchronous Password Management Views — Enterprise Edition
=========================================================

Endpoints covered:
  POST /api/v1/password/reset-request/
      → initiate email or phone-based reset (anonymous, rate-limited)

  POST /api/v1/password/reset-confirm/<uidb64>/<token>/
      → finalize email reset via link-token pair

  POST /api/v1/password/reset-phone-confirm/
      → finalize phone reset via OTP code

  POST /api/v1/password/change/
      → authenticated user changes own password from dashboard
        Permission: IsVerifiedUser  (active + OTP-verified)
        Decorator:  @require_verification  (inline double-check)

Security posture:
  - All public endpoints return the SAME generic success message regardless
    of whether the account exists (prevents user-enumeration).
  - Rate limiting applied via RateLimitPermission (100 req/hour per IP).
  - Password change wraps the save() in transaction.atomic() + on_commit
    for the notification email.
  - AuditService.log() called on every password event for SIEM compliance.
  - All actions are logged via the 'application' logger for SIEM ingestion.
"""

import logging
import uuid

from apps.authentication.serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordResetRequestSerializer,
)
from apps.authentication.services.password_service import (
    SyncPasswordService,
)
from apps.common.permissions import (
    IsVerifiedUser,
    RateLimitPermission,
    require_verification,
)
from apps.common.renderers import CustomJSONRenderer
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger('application')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SUCCESS = lambda msg: {"status": "success", "message": msg}           # noqa: E731
_ERROR   = lambda msg, code=None: {                                     # noqa: E731
    "status": "error",
    "message": msg,
    **({} if not code else {"code": code}),
}


def _get_client_ip(request) -> str:
    """Return the real client IP respecting X-Forwarded-For."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _audit_log(
    *,
    event_type_name: str,
    action: str,
    request,
    actor=None,
    metadata: dict | None = None,
    severity_name: str = "INFO",
    is_compliance: bool = True,
):
    """
    Best-effort AuditService.log() call.

    Wrapped in broad try/except so a misconfigured audit log NEVER blocks
    the password operation itself. Failures are logged at WARNING level.
    """
    try:
        from apps.audit_logs.services import AuditService
        from apps.audit_logs.models import EventType, EventCategory, SeverityLevel

        event_type = getattr(EventType, event_type_name, None)
        severity   = getattr(SeverityLevel, severity_name, SeverityLevel.INFO)

        if event_type is None:
            logger.warning(
                "_audit_log: unknown event_type_name='%s'", event_type_name
            )
            return

        AuditService.log(
            event_type=event_type,
            event_category=EventCategory.SECURITY,
            severity=severity,
            action=action,
            request=request,
            actor=actor,
            actor_email=getattr(actor, "email", None) if actor else None,
            ip_address=_get_client_ip(request),
            metadata=metadata or {},
            is_compliance=is_compliance,
        )
    except Exception as exc:  # pragma: no cover — audit must never block
        logger.warning(
            "_audit_log call failed (%s). event=%s action=%s",
            exc, event_type_name, action,
        )


# ===========================================================================
# POST /api/v1/password/reset-request/
# ===========================================================================

class PasswordResetRequestView(APIView):
    """
    Initiate a password reset — email or phone.

    Accepts ``{ "email_or_phone": "..." }`` and dispatches either a
    magic-link email or an SMS OTP, depending on the identifier type.

    Always returns the same generic message (anti-enumeration).
    Rate-limited: 100 req/hour per IP.

    AuditService event: PASSWORD_RESET_REQUESTED (compliance=True)
    """
    serializer_class  = PasswordResetRequestSerializer
    permission_classes = [AllowAny, RateLimitPermission]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    throttle_scope     = 'password_reset'

    def post(self, request):
        request_id     = str(uuid.uuid4())[:8]
        email_or_phone = request.data.get("email_or_phone", "")
        logger.info("[%s] PasswordResetRequest: start — identifier=%s",
                    request_id, email_or_phone)

        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email_or_phone = serializer.validated_data["email_or_phone"]

        try:
            message = SyncPasswordService.request_reset(email_or_phone)
            logger.info("[%s] PasswordResetRequest: dispatched", request_id)

            # ── Audit log ──────────────────────────────────────────────────
            _audit_log(
                event_type_name="PASSWORD_RESET_REQUEST",
                action=f"Password reset requested for: {email_or_phone}",
                request=request,
                metadata={
                    "email_or_phone": email_or_phone,
                    "request_id": request_id,
                },
                severity_name="INFO",
                is_compliance=True,
            )

            return Response(_SUCCESS(message), status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(
                "[%s] PasswordResetRequest: unexpected error — %s",
                request_id, exc, exc_info=True,
            )
            # Anti-enumeration: always look successful to the caller
            return Response(
                _SUCCESS("If an account exists, a reset code has been sent."),
                status=status.HTTP_200_OK,
            )


# ===========================================================================
# POST /api/v1/password/reset-confirm/<uidb64>/<token>/
# ===========================================================================

class PasswordResetConfirmEmailView(APIView):
    """
    Finalise an email-based password reset.

    URL parameters:
      uidb64  — base64-encoded user PK (from the magic link).
      token   — HMAC one-time-use Django password-reset token.

    Body:
      password  — new password (validated against AUTH_PASSWORD_VALIDATORS)
      password2 — confirmation field

    Returns 200 on success, 400 on bad token / password mismatch.

    On success:  audit event PASSWORD_RESET_COMPLETED (compliance=True)
    On failure:  rich error body with forgot_password_page + request_new_reset URLs
    """
    serializer_class  = PasswordResetConfirmEmailSerializer
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, uidb64: str, token: str):
        request_id = str(uuid.uuid4())[:8]
        logger.info("[%s] PasswordResetConfirmEmail: uidb64=%s", request_id, uidb64)

        # Merge URL params into data so the serializer validates them
        data = {**request.data, "uidb64": uidb64, "token": token}
        serializer = PasswordResetConfirmEmailSerializer(data=data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            service_payload = {
                "uidb64":       uidb64,
                "token":        token,
                "new_password": serializer.validated_data["password"],
            }
            msg = SyncPasswordService.confirm_reset(service_payload)
            logger.info("[%s] PasswordResetConfirmEmail: success", request_id)

            # ── Audit log — success ────────────────────────────────────────
            _audit_log(
                event_type_name="PASSWORD_RESET_DONE",
                action="Password reset completed via email magic link",
                request=request,
                metadata={
                    "method": "email",
                    "uidb64": uidb64,
                    "request_id": request_id,
                },
                severity_name="INFO",
                is_compliance=True,
            )

            return Response(_SUCCESS(msg), status=status.HTTP_200_OK)

        except Exception as exc:
            logger.warning(
                "[%s] PasswordResetConfirmEmail: failed — %s", request_id, exc
            )
            # ── Bug 8b fix: rich error with actionable URLs ────────────────
            from django.conf import settings as _s
            _base = getattr(_s, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
            return Response(
                {
                    "status": "error",
                    "message": (
                        "Invalid or expired reset link. "
                        "Please request a new password reset."
                    ),
                    "code": "invalid_token",
                    "actions": {
                        "request_new_reset":   "/api/v1/password/reset-request/",
                        "forgot_password_page": f"{_base}/forgot-password",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ===========================================================================
# POST /api/v1/password/reset-phone-confirm/
# ===========================================================================

class PasswordResetConfirmPhoneView(APIView):
    """
    Finalise a phone-based password reset via OTP.

    Body:
      otp       — 6-digit code sent via SMS (phone is fetched from Redis OTP token)
      password  — new password
      password2 — confirmation

    On success:  audit event PASSWORD_RESET_COMPLETED (compliance=True)
    On failure:  rich error body with resend_otp + request_new_reset URLs
    """
    serializer_class  = PasswordResetConfirmPhoneSerializer
    permission_classes = [AllowAny]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        request_id = str(uuid.uuid4())[:8]
        logger.info("[%s] PasswordResetConfirmPhone: start", request_id)

        serializer = PasswordResetConfirmPhoneSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vd = serializer.validated_data
        service_payload = {
            # OTP-only: no phone in body. The service calls verify_by_otp_sync(otp)
            # which performs an O(1) SHA-256 Redis hash-index lookup to discover user_id.
            # Field names: new_password (matches Zod PasswordResetConfirmPhoneSchema)
            "token":        vd["otp"],
            "new_password": vd["new_password"],
        }


        try:
            msg = SyncPasswordService.confirm_reset(service_payload)
            logger.info("[%s] PasswordResetConfirmPhone: success", request_id)

            # ── Audit log — success ────────────────────────────────────────
            _audit_log(
                event_type_name="PASSWORD_RESET_DONE",
                action="Password reset completed via phone OTP",
                request=request,
                metadata={
                    "method": "phone",
                    "request_id": request_id,
                },
                severity_name="INFO",
                is_compliance=True,
            )

            return Response(_SUCCESS(msg), status=status.HTTP_200_OK)

        except Exception as exc:
            logger.warning(
                "[%s] PasswordResetConfirmPhone: failed — %s", request_id, exc
            )
            from django.conf import settings as _s
            _base = getattr(_s, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
            return Response(
                {
                    "status": "error",
                    "message": "Invalid or expired OTP. Please request a new code.",
                    "code": "invalid_otp",
                    "actions": {
                        "resend_otp":        f"{_base}/resend-otp",
                        "request_new_reset": "/api/v1/password/reset-request/",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ===========================================================================
# POST /api/v1/password/change/
# ===========================================================================

class ChangePasswordView(APIView):
    """
    Authenticated user changes their own password from the dashboard.

    Permission gate (strictest possible for account-mutating actions):
      IsVerifiedUser  — user must be authenticated, active, AND OTP-verified.

    The ``@require_verification`` decorator adds an inline double-check so
    that even if permission_classes is accidentally overridden in a subclass,
    the verification check still runs inside the method body.

    Flow:
      1. Validate old password + new password (DRF serializer).
      2. transaction.atomic() — set new password and save().
      3. AuditService.log(PASSWORD_CHANGED) — compliance record.
      4. transaction.on_commit() — fire confirmation email via Celery (non-blocking).
      5. Return 200 with success message.

    Body:
      old_password     — current password
      new_password     — new password (validated by Django validators)
      confirm_password — must match new_password
    """
    serializer_class  = PasswordChangeSerializer
    permission_classes = [IsVerifiedUser]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    @require_verification  # Double gate — inline method-level check
    def post(self, request):
        request_id = str(uuid.uuid4())[:8]
        logger.info(
            "[%s] ChangePassword: user=%s",
            request_id, getattr(request.user, "email", request.user.pk),
        )

        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vd   = serializer.validated_data
        user = request.user

        try:
            with transaction.atomic():
                user.set_password(vd["new_password"])
                user.save(update_fields=["password", "updated_at"])

                logger.info(
                    "[%s] ChangePassword: password updated for user=%s",
                    request_id, getattr(user, "email", user.pk),
                )

                # ── Audit log — compliance record (inside atomic) ──────────
                # Using plain call (not on_commit) so if the audit log write
                # fails we still have the audit event associated correctly.
                _audit_log(
                    event_type_name="PASSWORD_CHANGED",
                    action=f"Password changed by user {user.pk}",
                    request=request,
                    actor=user,
                    metadata={
                        "user_id": str(user.pk),
                        "user_email": getattr(user, "email", ""),
                        "request_id": request_id,
                    },
                    severity_name="INFO",
                    is_compliance=True,
                )

                # ── Fire-and-forget Celery confirmation email on commit ─────
                # Using Celery async task to keep request-response non-blocking.
                if getattr(user, "email", None):
                    from apps.authentication.tasks import send_email_task
                    _user_email = user.email
                    _user_ctx = {
                        "user_first_name": getattr(user, "first_name", ""),
                        "user_email":      _user_email,
                    }
                    transaction.on_commit(lambda: send_email_task.delay(
                        subject="Password Changed — Fashionistar",
                        recipients=[_user_email],
                        template_name="authentication/email/password_changed.html",
                        context=_user_ctx,
                    ))
                    logger.info(
                        "[%s] ChangePassword: confirmation email scheduled via Celery",
                        request_id,
                    )

            return Response(
                _SUCCESS("Password changed successfully."),
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            logger.error(
                "[%s] ChangePassword: unexpected error — %s",
                request_id, exc, exc_info=True,
            )
            return Response(
                _ERROR("Unable to change password. Please try again."),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
