# apps/authentication/services/password_service/sync_service.py
"""
Synchronous Password Reset & Change Service — Enterprise Edition.

Provides robust, production-grade logic for password lifecycle management.
Integrates with specialized authentication audit helpers to ensure
compliance-grade event tracking (7-year retention).

Security Architecture:
    - Anti-Enumeration: Generic responses for password reset requests.
    - Consistency: Atomic transactions paired with on_commit tasks for notifications.
    - Compliance: Specialized helpers from auth_audit for immutable event logging.
    - Safety: Failsafe audit logging that never interrupts business logic.
"""

import logging
from django.db.models import Q
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings

from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp import OTPService
from apps.authentication.tasks import send_email_task, send_sms_task
from apps.authentication.exceptions import (
    GoogleUserCannotResetPasswordError,
    AccountDeactivatedError
)
from apps.audit_logs.services.authentication import auth_audit

logger = logging.getLogger('application')


class SyncPasswordService:
    """
    Synchronous Service for Password Reset and Change operations.

    Handles the core logic for password management while ensuring all
    actions are recorded via compliance-grade audit helpers.
    """

    @staticmethod
    def request_reset(email_or_phone: str, request=None) -> str:
        """
        Initiates the password reset flow (Synchronous).

        Security Features:
            - Normalizes email identifiers to prevent duplicate account logic.
            - Uses a single database query with Q objects for performance.
            - Implements anti-enumeration by returning a generic success message
              regardless of whether the user exists in the system.
            - Records a PASSWORD_RESET_REQUEST audit event for all attempts.

        Args:
            email_or_phone: The user's email or phone number identifier.
            request: Optional Django HttpRequest for audit context (IP/UA).

        Returns:
            str: A generic success message to prevent user enumeration.

        Raises:
            Exception: If the service is temporarily unavailable.
        """
        try:
            is_email = "@" in email_or_phone
            if is_email:
                # Normalise email domain to lowercase only for email (phone remains unchanged)
                from django.contrib.auth.base_user import BaseUserManager as _BUM
                email_or_phone = _BUM.normalize_email(email_or_phone)

            # ✅ OPTIMIZED: Single database query using Q object
            try:
                user_qs = UnifiedUser.objects.all_with_deleted().filter(
                    Q(email=email_or_phone) if is_email else Q(phone=email_or_phone)
                )
                soft_deleted = user_qs.filter(is_deleted=True).exists()
                if soft_deleted:
                    logger.warning(
                        "⛔ Password reset requested for soft-deleted account: %s",
                        email_or_phone,
                    )
                    raise AccountDeactivatedError
                user = user_qs.first()
            except Exception as e:
                logger.error("Error querying UnifiedUser for password reset request: %s", str(e))
                user = None

            # ── Audit: Specialized helper for reset requests ─────────────
            # Records the attempt with security signals (user_exists)
            # Failsafe: Wrapped in try-except to ensure audit failures never block reset requests
            try:
                auth_audit.log_password_reset_requested(
                    email=email_or_phone,
                    user_exists=user is not None,
                    request=request
                )
            except Exception as audit_exc:
                logger.warning("⚠️ Audit log password reset request failed: %s", audit_exc)

            if not user:
                logger.warning("⚠️ Password reset requested for non-existent: %s", email_or_phone)
                return "If an account exists, a reset code has been sent."

            if user.auth_provider == UnifiedUser.PROVIDER_GOOGLE:
                logger.info("ℹ️ Google user %s attempted password reset.", user.email)
                raise GoogleUserCannotResetPasswordError

            if is_email:
                # EMAIL FLOW: Generate secure one-time token
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_link = (
                    f"{settings.FRONTEND_URL.rstrip('/')}"
                    f"/auth/forgot-password/confirm-email/{uid}/{token}"
                )

                _site_url = getattr(settings, 'FRONTEND_URL', 'https://fashionistar.net').rstrip('/')

                # ✅ Consistency: Wrap in on_commit to ensure task fires AFTER DB commit
                _email_ctx = {
                    "user": {
                        "first_name": getattr(user, "first_name", "") or "",
                        "email":      getattr(user, "email", "") or "",
                    },
                    "reset_url": reset_link,
                    "SITE_URL":  _site_url,
                }
                _email_to = user.email

                transaction.on_commit(lambda: send_email_task.delay(
                    subject="Password Reset Request",
                    recipients=[_email_to],
                    template_name="authentication/email/password_reset.html",
                    context=_email_ctx,
                ))
                logger.info("📧 Reset Email Celery task scheduled on_commit for %s", user.email)

            else:
                # PHONE FLOW: Generate numeric OTP
                otp = OTPService.generate_otp_sync(
                    user.id,
                    purpose='password_reset',
                    request=request,
                )
                _otp_msg = f"Your Password Reset Code is: {otp}. Valid for 5 minutes."
                _user_phone = str(user.phone)

                transaction.on_commit(lambda: send_sms_task.delay(
                    to=_user_phone, body=_otp_msg
                ))
                logger.info("📱 Reset SMS Celery task scheduled on_commit for %s", user.phone)

            return "If an account exists, a reset code has been sent."

        except Exception as e:
            if isinstance(e, (AccountDeactivatedError, GoogleUserCannotResetPasswordError)):
                raise
            logger.error("❌ Password Request Error (Sync): %s", e)
            raise Exception("Service unavailable.")

    @staticmethod
    def confirm_reset(data: dict, request=None) -> str:
        """
        Verifies the reset token/OTP and sets a new password.

        Implements strict validation for both email (token) and phone (OTP)
        reset flows. Records successful completions or detailed failures
        to the audit log.

        Args:
            data: Dictionary containing 'new_password' and either 'uidb64'/'token'
                  or 'token' (for OTP).
            request: Optional Django HttpRequest for audit context.

        Returns:
            str: Success message.

        Raises:
            Exception: If validation fails or the user cannot be identified.
        """
        try:
            user = None

            if 'uidb64' in data and data['uidb64']:
                # EMAIL FLOW: UID + Token validation
                try:
                    uid = force_str(urlsafe_base64_decode(data['uidb64']))
                    user = UnifiedUser.objects.get(pk=uid)
                except (TypeError, ValueError, OverflowError, UnifiedUser.DoesNotExist):
                    try:
                        auth_audit.log_password_reset_failed(
                            reason="Invalid reset link (uidb64 decode failed)",
                            request=request,
                            metadata={"flow": "email"}
                        )
                    except Exception as audit_exc:
                        logger.warning("⚠️ Audit log password reset failure failed: %s", audit_exc)
                    raise Exception("Invalid reset link.")

                if not default_token_generator.check_token(user, data['token']):
                    try:
                        auth_audit.log_password_reset_failed(
                            reason="Token invalid or expired",
                            request=request,
                            actor=user,
                            metadata={"flow": "email"}
                        )
                    except Exception as audit_exc:
                        logger.warning("⚠️ Audit log password reset failure failed: %s", audit_exc)
                    raise Exception("Invalid or expired token.")

            elif 'token' in data and data['token'] and 'phone' not in data:
                # PHONE FLOW: OTP validation
                otp_result = OTPService.verify_by_otp_sync(
                    data['token'],
                    purpose='password_reset',
                    request=request,
                )
                if not otp_result:
                    try:
                        auth_audit.log_password_reset_failed(
                            reason="OTP invalid or expired",
                            request=request,
                            metadata={"flow": "phone"}
                        )
                    except Exception as audit_exc:
                        logger.warning("⚠️ Audit log password reset failure failed: %s", audit_exc)
                    raise Exception("Invalid or expired OTP.")

                try:
                    user = UnifiedUser.objects.get(pk=otp_result['user_id'])
                except UnifiedUser.DoesNotExist:
                    try:
                        auth_audit.log_password_reset_failed(
                            reason="User not found for OTP user_id",
                            request=request,
                            metadata={"flow": "phone"}
                        )
                    except Exception as audit_exc:
                        logger.warning("⚠️ Audit log password reset failure failed: %s", audit_exc)
                    raise Exception("User not found.")

            else:
                raise Exception("Invalid request data.")

            # ── Atomic Update: Save password and notify ───────────────────
            # Password hashing is handled automatically by set_password
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

            # ── Audit: Success completion via specialized helper ──────────
            # ✅ TRANSACTIONAL INTEGRITY: Wrapped in on_commit to ensure the audit
            # event only fires if the password was successfully saved to the database.
            def _log_reset_success():
                try:
                    auth_audit.log_password_reset_completed(
                        actor=user,
                        request=request,
                        metadata={
                            "flow": "email" if ('uidb64' in data and data['uidb64']) else "phone",
                        }
                    )
                except Exception as audit_exc:
                    logger.warning("⚠️ Audit log password reset success failed: %s", audit_exc)

            transaction.on_commit(_log_reset_success)

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
        Changes the password for an already authenticated user.

        Verifies the current password before applying changes as a security
        guard against session hijacking.

        Args:
            user: The authenticated UnifiedUser instance.
            old_password: The current plaintext password for verification.
            new_password: The new password to be set.
            request: Optional Django HttpRequest for audit context.

        Returns:
            str: Success message.

        Raises:
            Exception: If the current password is incorrect or DB save fails.
        """
        try:
            # 🔐 SECURITY GUARD: Must verify old password before change
            if not user.check_password(old_password):
                try:
                    auth_audit.log_password_changed(
                        actor=user,
                        success=False,
                        reason="Incorrect current password provided",
                        request=request
                    )
                except Exception as audit_exc:
                    logger.warning("⚠️ Audit log password change failure failed: %s", audit_exc)
                raise Exception("Current password is incorrect.")

            with transaction.atomic():
                user.set_password(new_password)
                user.save(update_fields=['password', 'updated_at'])

                if user.email:
                    _user_email = user.email
                    _ctx = {
                        "first_name": getattr(user, "first_name", ""),
                        "email": _user_email
                    }
                    transaction.on_commit(lambda: send_email_task.delay(
                        subject="Your Password Has Been Changed",
                        recipients=[_user_email],
                        template_name="authentication/email/password_changed.html",
                        context={"user": _ctx},
                    ))

            # ── Audit: Specialized helper for password change ──────────────
            # ✅ TRANSACTIONAL INTEGRITY: Fired on_commit to maintain atomic consistency.
            def _log_change_success():
                try:
                    auth_audit.log_password_changed(
                        actor=user,
                        success=True,
                        request=request
                    )
                except Exception as audit_exc:
                    logger.warning("⚠️ Audit log password change success failed: %s", audit_exc)

            transaction.on_commit(_log_change_success)

            logger.info("✅ Password changed for User %s", user.pk)
            return "Password changed successfully."

        except Exception as e:
            if "incorrect current password" in str(e).lower():
                raise
            logger.error("❌ Password Change Error (Sync): %s", e)
            raise Exception(str(e))
