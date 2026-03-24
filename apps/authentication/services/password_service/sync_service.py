# apps/authentication/services/password_service/sync_service.py
"""
Synchronous Password Reset & Change Service — Enterprise Edition.

All critical security operations (reset request, confirm, change) are
fully audit-logged to AuditEventLog with event_type, actor, IP, UA,
compliance flag, and error details.
"""

import logging
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp import OTPService
from apps.common.managers.email import EmailManager
from apps.common.managers.sms import SMSManager
from apps.authentication.tasks import send_email_task, send_sms_task

logger = logging.getLogger('application')


# ══════════════════════════════════════════════════════════════════════════
# Audit helpers — never raise, never block the HTTP path
# ══════════════════════════════════════════════════════════════════════════

def _audit_password(
    *,
    event_type: str,
    action: str,
    request=None,
    actor=None,
    actor_email: str | None = None,
    severity: str = "info",
    error_message: str | None = None,
    metadata: dict | None = None,
    is_compliance: bool = True,
) -> None:
    """Write a structured audit event for a password-related operation."""
    try:
        from apps.audit_logs.services.audit import AuditService
        from apps.audit_logs.models import EventCategory

        ip = None
        ua = None
        if request:
            xff = getattr(request, 'META', {}).get('HTTP_X_FORWARDED_FOR', '')
            ip = xff.split(',')[0].strip() if xff else getattr(
                request, 'META', {}
            ).get('REMOTE_ADDR')
            ua = getattr(request, 'META', {}).get('HTTP_USER_AGENT', '')

        resource_id = str(actor.pk) if actor and hasattr(actor, 'pk') else None

        AuditService.log(
            event_type=event_type,
            event_category=EventCategory.SECURITY,
            severity=severity,
            action=action,
            request=request,
            actor=actor,
            actor_email=actor_email or (getattr(actor, 'email', None) if actor else None),
            ip_address=ip,
            user_agent=ua,
            resource_type="UnifiedUser",
            resource_id=resource_id,
            metadata=metadata,
            error_message=error_message,
            is_compliance=is_compliance,
        )
    except Exception:
        pass  # Audit failure must NEVER fail the password operation


class SyncPasswordService:
    """
    Synchronous Service for Password Reset and Change.

    All critical operations produce AuditEventLog entries for compliance.
    """

    @staticmethod
    def request_reset(email_or_phone: str, request=None):
        """
        Initiates the reset flow (Sync).

        Always returns the same generic string for security (no user enumeration).
        Writes PASSWORD_RESET_REQUEST to AuditEventLog whether or not the user exists.
        """
        try:
            user = None
            is_email = '@' in email_or_phone

            if is_email:
                try:
                    user = UnifiedUser.objects.get(email=email_or_phone)
                except UnifiedUser.DoesNotExist:
                    pass
            else:
                try:
                    user = UnifiedUser.objects.get(phone=email_or_phone)
                except UnifiedUser.DoesNotExist:
                    pass

            # ── Audit: always log that a reset was requested ─────────────
            from apps.audit_logs.models import EventType
            _audit_password(
                event_type=EventType.PASSWORD_RESET_REQUEST,
                action=(
                    f"Password reset requested for {'known' if user else 'unknown'} "
                    f"identifier (email={is_email})"
                ),
                request=request,
                actor=user,
                actor_email=getattr(user, 'email', None) if user else None,
                severity="info",
                metadata={
                    "identifier_type": "email" if is_email else "phone",
                    "user_exists": user is not None,
                    # Note: DO NOT log the actual identifier — prevents log-based enumeration
                },
                is_compliance=True,
            )

            if not user:
                logger.warning("⚠️ Password reset requested for non-existent: %s", email_or_phone)
                return "If an account exists, a reset code has been sent."

            if user.auth_provider == UnifiedUser.PROVIDER_GOOGLE:
                logger.info("ℹ️ Google user %s attempted password reset.", user.email)
                return "If an account exists, a reset code has been sent."

            if is_email:
                # EMAIL FLOW
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?uid={uid}&token={token}"

                _site_url = getattr(settings, 'FRONTEND_URL', 'https://fashionistar.net').rstrip('/')
                send_email_task.delay(
                    subject="Password Reset Request",
                    recipients=[user.email],
                    template_name="authentication/email/password_reset.html",
                    context={
                        "user": {
                            "first_name": getattr(user, "first_name", "") or "",
                            "email": getattr(user, "email", "") or "",
                        },
                        "reset_url": reset_link,
                        "SITE_URL": _site_url,
                    }
                )
                logger.info("📧 Reset Email Celery task dispatched for %s", user.email)

            else:
                # PHONE FLOW
                otp = OTPService.generate_otp_sync(user.id, purpose='password_reset')
                message = f"Your Password Reset Code is: {otp}. Valid for 5 minutes."
                send_sms_task.delay(to=str(user.phone), body=message)
                logger.info("📱 Reset SMS Celery task dispatched for %s", user.phone)

            return "If an account exists, a reset code has been sent."

        except Exception as e:
            logger.error("❌ Password Request Error (Sync): %s", e)
            raise Exception("Service unavailable.")

    @staticmethod
    def confirm_reset(data: dict, request=None):
        """
        Verifies token/OTP and resets password (Sync).

        Writes PASSWORD_RESET_DONE (success) or WARNING (failure) to AuditEventLog.
        """
        from apps.audit_logs.models import EventType

        try:
            user = None

            if 'uidb64' in data and data['uidb64']:
                # Email Flow
                try:
                    uid = force_str(urlsafe_base64_decode(data['uidb64']))
                    user = UnifiedUser.objects.get(pk=uid)
                except (TypeError, ValueError, OverflowError, UnifiedUser.DoesNotExist):
                    _audit_password(
                        event_type=EventType.PASSWORD_RESET_DONE,
                        action="Password reset failed — invalid uidb64 link",
                        request=request,
                        severity="warning",
                        error_message="Invalid reset link (uidb64 decode failed)",
                        metadata={"flow": "email"},
                        is_compliance=True,
                    )
                    raise Exception("Invalid reset link.")

                if not default_token_generator.check_token(user, data['token']):
                    _audit_password(
                        event_type=EventType.PASSWORD_RESET_DONE,
                        action="Password reset failed — invalid or expired token",
                        request=request,
                        actor=user,
                        severity="warning",
                        error_message="Token invalid or expired",
                        metadata={"flow": "email"},
                        is_compliance=True,
                    )
                    raise Exception("Invalid or expired token.")

            elif 'token' in data and data['token'] and 'phone' not in data:
                # Phone OTP-only flow
                otp_result = OTPService.verify_by_otp_sync(
                    data['token'], purpose='password_reset'
                )
                if not otp_result:
                    _audit_password(
                        event_type=EventType.PASSWORD_RESET_DONE,
                        action="Password reset failed — invalid or expired OTP",
                        request=request,
                        severity="warning",
                        error_message="OTP invalid or expired",
                        metadata={"flow": "phone"},
                        is_compliance=True,
                    )
                    raise Exception("Invalid or expired OTP.")

                try:
                    user = UnifiedUser.objects.get(pk=otp_result['user_id'])
                except UnifiedUser.DoesNotExist:
                    _audit_password(
                        event_type=EventType.PASSWORD_RESET_DONE,
                        action="Password reset failed — user not found from OTP",
                        request=request,
                        severity="warning",
                        error_message="User not found for OTP user_id",
                        metadata={"flow": "phone"},
                        is_compliance=True,
                    )
                    raise Exception("User not found.")

            else:
                raise Exception("Invalid request data.")

            # ── Atomic: save password + fire on_commit email ──────────────
            with transaction.atomic():
                user.set_password(data['new_password'])
                user.save(update_fields=['password', 'updated_at'])

                if user.email:
                    _user_email = user.email
                    _user_context = {
                        "first_name": getattr(user, "first_name", ""),
                        "email": _user_email,
                    }
                    transaction.on_commit(lambda: send_email_task.delay(
                        subject="Password Changed",
                        recipients=[_user_email],
                        template_name="authentication/email/password_changed.html",
                        context={"user": _user_context}
                    ))

            # ── Audit: success ─────────────────────────────────────────────
            _audit_password(
                event_type=EventType.PASSWORD_RESET_DONE,
                action="Password reset completed successfully",
                request=request,
                actor=user,
                severity="info",
                metadata={
                    "flow": "email" if ('uidb64' in data and data['uidb64']) else "phone",
                },
                is_compliance=True,
            )

            logger.info("✅ Password reset successful for User %s", user.id)
            return "Password has been reset successfully."

        except Exception as e:
            logger.error("❌ Password Confirm Error (Sync): %s", e)
            raise Exception(str(e))

    @staticmethod
    def change_password(
        user: UnifiedUser,
        old_password: str,
        new_password: str,
        request=None,
    ) -> str:
        """
        Change password for an authenticated user.

        Verifies old password first (security guard). Writes PASSWORD_CHANGED
        to AuditEventLog on success, WARNING on failure.

        Args:
            user:         The authenticated UnifiedUser.
            old_password: Current (plaintext) password for verification.
            new_password: New password to set.
            request:      Django/DRF request for IP/UA audit context.

        Returns:
            str: Success message.

        Raises:
            Exception: If old password is wrong or DB write fails.
        """
        from apps.audit_logs.models import EventType

        try:
            if not user.check_password(old_password):
                _audit_password(
                    event_type=EventType.PASSWORD_CHANGED,
                    action="Password change failed — incorrect current password",
                    request=request,
                    actor=user,
                    severity="warning",
                    error_message="Incorrect current password provided",
                    metadata={"reason": "wrong_current_password"},
                    is_compliance=True,
                )
                raise Exception("Current password is incorrect.")

            with transaction.atomic():
                user.set_password(new_password)
                user.save(update_fields=['password', 'updated_at'])

                if user.email:
                    _user_email = user.email
                    _ctx = {"first_name": getattr(user, "first_name", ""), "email": _user_email}
                    transaction.on_commit(lambda: send_email_task.delay(
                        subject="Your Password Has Been Changed",
                        recipients=[_user_email],
                        template_name="authentication/email/password_changed.html",
                        context={"user": _ctx},
                    ))

            _audit_password(
                event_type=EventType.PASSWORD_CHANGED,
                action="Password changed successfully",
                request=request,
                actor=user,
                severity="info",
                metadata={"method": "authenticated_change"},
                is_compliance=True,
            )

            logger.info("✅ Password changed for User %s", user.pk)
            return "Password changed successfully."

        except Exception as e:
            if "incorrect current password" in str(e).lower():
                raise
            logger.error("❌ Password Change Error (Sync): %s", e)
            raise Exception(str(e))
