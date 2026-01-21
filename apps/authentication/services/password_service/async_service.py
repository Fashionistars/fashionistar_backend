# apps/authentication/services/password_service/async_service.py

import logging
import asyncio
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp_service import AsyncOTPService
from apps.common.managers.email import EmailManager
from apps.common.managers.sms import SMSManager

logger = logging.getLogger('application')

class AsyncPasswordService:
    """
    Asynchronous Service for Password Reset and Change.
    """

    @staticmethod
    async def request_reset(email_or_phone: str):
        """
        Initiates the reset flow (Async).
        """
        try:
            user = None
            is_email = '@' in email_or_phone

            if is_email:
                try:
                    user = await UnifiedUser.objects.aget(email=email_or_phone)
                except UnifiedUser.DoesNotExist:
                    pass 
            else:
                try:
                    user = await UnifiedUser.objects.aget(phone=email_or_phone)
                except UnifiedUser.DoesNotExist:
                    pass

            if not user:
                logger.warning(f"⚠️ Password reset requested for non-existent: {email_or_phone} (Async)")
                return "If an account exists, a reset code has been sent."

            if user.auth_provider == UnifiedUser.PROVIDER_GOOGLE:
                logger.info(f"ℹ️ Google user {user.email} attempted password reset.")
                return "If an account exists, a reset code has been sent."

            if is_email:
                # EMAIL FLOW
                token = await asyncio.to_thread(default_token_generator.make_token, user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?uid={uid}&token={token}"
                
                await EmailManager.asend_mail(
                    subject="Password Reset Request",
                    recipients=[user.email],
                    template_name="accounts/email/password_reset.html",
                    context={"user": user, "reset_link": reset_link}
                )
                logger.info(f"📧 Reset Email sent to {user.email}")

            else:
                # PHONE FLOW
                otp = await AsyncOTPService.generate_otp(str(user.id), purpose='password_reset')
                message = f"Your Password Reset Code is: {otp}. Valid for 5 minutes."
                await SMSManager.asend_sms(to=str(user.phone), body=message)
                logger.info(f"📱 Reset SMS sent to {user.phone}")

            return "If an account exists, a reset code has been sent."

        except Exception as e:
            logger.error(f"❌ Password Request Error (Async): {e}")
            raise Exception("Service unavailable.")

    @staticmethod
    async def confirm_reset(data: dict):
        """
        Verifies token/OTP and resets password (Async).
        """
        try:
            user = None
            
            if 'uidb64' in data and data['uidb64']:
                # Email Flow
                try:
                    uid = force_str(urlsafe_base64_decode(data['uidb64']))
                    user = await UnifiedUser.objects.aget(pk=uid)
                except (TypeError, ValueError, OverflowError, UnifiedUser.DoesNotExist):
                    raise Exception("Invalid reset link.")
                
                is_valid_token = await asyncio.to_thread(default_token_generator.check_token, user, data['token'])
                if not is_valid_token:
                    raise Exception("Invalid or expired token.")
            
            elif 'phone' in data and data['phone']:
                # Phone Flow
                try:
                    user = await UnifiedUser.objects.aget(phone=data['phone'])
                except UnifiedUser.DoesNotExist:
                     raise Exception("Invalid phone.")

                is_valid_otp = await AsyncOTPService.verify_otp(str(user.id), data['token'], purpose='password_reset')
                if not is_valid_otp:
                    raise Exception("Invalid or expired OTP.")
            
            else:
                raise Exception("Invalid request data.")

            user.set_password(data['new_password'])
            await user.asave()
            
            if user.email:
                await EmailManager.asend_mail(
                    subject="Password Changed",
                    recipients=[user.email],
                    template_name="accounts/email/password_changed.html",
                    context={"user": user}
                )
                
            logger.info(f"✅ Password reset successful for User {user.id} (Async)")
            return "Password has been reset successfully."

        except Exception as e:
            logger.error(f"❌ Password Confirm Error (Async): {e}")
            raise Exception(str(e))
