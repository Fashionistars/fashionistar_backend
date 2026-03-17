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
  - All actions are logged via the 'application' logger for SIEM ingestion.
"""

import logging
import uuid

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsVerifiedUser, RateLimitPermission, require_verification
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.serializers import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordChangeSerializer,
)
from apps.authentication.services.password_service import (
    SyncPasswordService,
)

logger = logging.getLogger('application')

# ---------------------------------------------------------------------------
# Helper — uniform success/error envelope
# ---------------------------------------------------------------------------
_SUCCESS = lambda msg: {"status": "success", "message": msg}  # noqa: E731
_ERROR   = lambda msg, code=None: {                           # noqa: E731
    "status": "error",
    "message": msg,
    **({"code": code} if code else {}),
}


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
    """

    permission_classes  = [AllowAny, RateLimitPermission]
    renderer_classes    = [CustomJSONRenderer]
    throttle_scope      = 'password_reset'

    def post(self, request):
        request_id = str(uuid.uuid4())[:8]
        logger.info("[%s] PasswordResetRequest: start", request_id)

        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            message = SyncPasswordService.request_reset(
                serializer.validated_data['email_or_phone']
            )
            logger.info("[%s] PasswordResetRequest: dispatched", request_id)
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
    """

    permission_classes  = [AllowAny]
    renderer_classes    = [CustomJSONRenderer]

    def post(self, request, uidb64: str, token: str):
        request_id = str(uuid.uuid4())[:8]
        logger.info("[%s] PasswordResetConfirmEmail: uidb64=%s", request_id, uidb64)

        # Merge URL params into data so the serializer validates them
        data = {**request.data, 'uidb64': uidb64, 'token': token}
        serializer = PasswordResetConfirmEmailSerializer(data=data)
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            service_payload = {
                'uidb64':        uidb64,
                'token':         token,
                'new_password':  serializer.validated_data['password'],
            }
            msg = SyncPasswordService.confirm_reset(service_payload)
            logger.info("[%s] PasswordResetConfirmEmail: success", request_id)
            return Response(_SUCCESS(msg), status=status.HTTP_200_OK)

        except Exception as exc:
            logger.warning(
                "[%s] PasswordResetConfirmEmail: failed — %s", request_id, exc
            )
            return Response(
                _ERROR(str(exc), code="invalid_token"),
                status=status.HTTP_400_BAD_REQUEST,
            )


# ===========================================================================
# POST /api/v1/password/reset-phone-confirm/
# ===========================================================================

class PasswordResetConfirmPhoneView(APIView):
    """
    Finalise a phone-based password reset via OTP.

    Body:
      phone    — the user's registered phone number
      otp      — 6-digit code sent via SMS
      password — new password
      password2 — confirmation
    """

    permission_classes  = [AllowAny]
    renderer_classes    = [CustomJSONRenderer]

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
            'phone':        request.data.get('phone'),
            'token':        vd['otp'],
            'new_password': vd['password'],
        }

        try:
            msg = SyncPasswordService.confirm_reset(service_payload)
            logger.info("[%s] PasswordResetConfirmPhone: success", request_id)
            return Response(_SUCCESS(msg), status=status.HTTP_200_OK)

        except Exception as exc:
            logger.warning(
                "[%s] PasswordResetConfirmPhone: failed — %s", request_id, exc
            )
            return Response(
                _ERROR(str(exc), code="invalid_otp"),
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
      3. transaction.on_commit() — fire confirmation email (non-blocking).
      4. Return 200 with success message.

    Body:
      old_password     — current password
      new_password     — new password (validated by Django validators)
      confirm_password — must match new_password
    """

    permission_classes  = [IsVerifiedUser]
    renderer_classes    = [CustomJSONRenderer]

    @require_verification  # Double gate — inline method-level check
    def post(self, request):
        request_id = str(uuid.uuid4())[:8]
        logger.info(
            "[%s] ChangePassword: user=%s",
            request_id, getattr(request.user, 'email', request.user.pk),
        )

        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request},
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
                user.set_password(vd['new_password'])
                user.save(update_fields=['password', 'updated_at'])

                logger.info(
                    "[%s] ChangePassword: password updated for user=%s",
                    request_id, getattr(user, 'email', user.pk),
                )

                # ── Fire-and-forget confirmation email on commit ──────────
                if getattr(user, 'email', None):
                    from apps.common.managers.email import EmailManager

                    def _send_confirmation_email():
                        try:
                            EmailManager.send_mail(
                                subject="Password Changed — Fashionistar",
                                recipients=[user.email],
                                template_name=(
                                    "authentication/email/password_changed.html"
                                ),
                                context={"user": user},
                                fail_silently=True,
                            )
                        except Exception as mail_exc:
                            logger.error(
                                "[%s] ChangePassword: confirmation email failed — %s",
                                request_id, mail_exc,
                            )

                    transaction.on_commit(_send_confirmation_email)

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
