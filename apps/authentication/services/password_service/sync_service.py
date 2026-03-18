# apps/authentication/services/password_service/sync_service.py

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

class SyncPasswordService:
    """
    Synchronous Service for Password Reset and Change.
    """

    @staticmethod
    def request_reset(email_or_phone: str):
        """
        Initiates the reset flow (Sync).
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

            if not user:
                logger.warning(f"⚠️ Password reset requested for non-existent: {email_or_phone}")
                return "If an account exists, a reset code has been sent."

            if user.auth_provider == UnifiedUser.PROVIDER_GOOGLE:
                logger.info(f"ℹ️ Google user {user.email} attempted password reset.")
                return "If an account exists, a reset code has been sent."

            if is_email:
                # EMAIL FLOW
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?uid={uid}&token={token}"
                
                send_email_task.delay(
                    subject="Password Reset Request",
                    recipients=[user.email],
                    template_name="authentication/email/password_reset.html",
                    context={"user": {"first_name": getattr(user, "first_name", ""), "email": getattr(user, "email", "")}, "reset_link": reset_link}
                )
                logger.info(f"📧 Reset Email Celery task dispatched for {user.email}")

            else:
                # PHONE FLOW
                otp = OTPService.generate_otp_sync(user.id, purpose='password_reset')
                message = f"Your Password Reset Code is: {otp}. Valid for 5 minutes."
                send_sms_task.delay(to=str(user.phone), body=message)
                logger.info(f"📱 Reset SMS Celery task dispatched for {user.phone}")

            return "If an account exists, a reset code has been sent."

        except Exception as e:
            logger.error(f"❌ Password Request Error (Sync): {e}")
            raise Exception("Service unavailable.")

    @staticmethod
    def confirm_reset(data: dict):
        """
        Verifies token/OTP and resets password (Sync).
        """
        try:
            user = None
            
            if 'uidb64' in data and data['uidb64']:
                # Email Flow
                try:
                    uid = force_str(urlsafe_base64_decode(data['uidb64']))
                    user = UnifiedUser.objects.get(pk=uid)
                except (TypeError, ValueError, OverflowError, UnifiedUser.DoesNotExist):
                    raise Exception("Invalid reset link.")
                
                if not default_token_generator.check_token(user, data['token']):
                    raise Exception("Invalid or expired token.")
            
            elif 'phone' in data and data['phone']:
                # Phone Flow
                try:
                    user = UnifiedUser.objects.get(phone=data['phone'])
                except UnifiedUser.DoesNotExist:
                    raise Exception("Invalid phone.")
                     
                if not OTPService.verify_otp_sync(user.id, data['token'], purpose='password_reset'):
                    raise Exception("Invalid or expired OTP.")
            
            else:
                raise Exception("Invalid request data.")

            # ── Atomic: save password + fire on_commit email ──────────────
            with transaction.atomic():
                user.set_password(data['new_password'])
                user.save(update_fields=['password', 'updated_at'])

                if user.email:
                    _user_email = user.email
                    _user_context = {"first_name": getattr(user, "first_name", ""), "email": _user_email}
                    transaction.on_commit(lambda: send_email_task.delay(
                        subject="Password Changed",
                        recipients=[_user_email],
                        template_name="authentication/email/password_changed.html",
                        context={"user": _user_context}
                    ))

            logger.info(f"✅ Password reset successful for User {user.id}")
            return "Password has been reset successfully."

        except Exception as e:
            logger.error(f"❌ Password Confirm Error (Sync): {e}")
            raise Exception(str(e))
