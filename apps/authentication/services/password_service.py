from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp_service import OTPService
from apps.common.managers.email import EmailManager
from apps.common.managers.sms import SMSManager
from asgiref.sync import sync_to_async
from django.conf import settings
import logging

logger = logging.getLogger('application')

class PasswordService:
    """
    Handles secure Password Reset and Change operations.
    Supports both Email (Link/Token) and Phone (OTP) flows.
    """

    @staticmethod
    async def request_reset_async(email_or_phone: str):
        """
        Initiates the reset flow.
        """
        try:
            user = None
            is_email = '@' in email_or_phone

            if is_email:
                try:
                    user = await UnifiedUser.objects.aget(email=email_or_phone)
                except UnifiedUser.DoesNotExist:
                    pass # Security: Do not reveal user existence
            else:
                try:
                    user = await UnifiedUser.objects.aget(phone=email_or_phone)
                except UnifiedUser.DoesNotExist:
                    pass

            if not user:
                logger.warning(f"⚠️ Password reset requested for non-existent: {email_or_phone}")
                return "If an account exists, a reset code has been sent."

            # Google Auth users cannot reset password (they don't have one)
            if user.auth_provider == UnifiedUser.PROVIDER_GOOGLE:
                logger.info(f"ℹ️ Google user {user.email} attempted password reset.")
                return "If an account exists, a reset code has been sent."

            if is_email:
                # EMAIL FLOW
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                # Construct Link (Frontend URL)
                reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?uid={uid}&token={token}"
                
                # Send Email
                EmailManager.send_mail(
                    subject="Password Reset Request",
                    recipients=[user.email],
                    template_name="accounts/email/password_reset.html",
                    context={"user": user, "reset_link": reset_link}
                )
                logger.info(f"📧 Reset Email sent to {user.email}")

            else:
                # PHONE FLOW
                otp = OTPService.generate_otp(user.id, purpose='password_reset')
                
                # Send SMS
                message = f"Your Password Reset Code is: {otp}. Valid for 5 minutes."
                SMSManager.send_sms(to=str(user.phone), body=message)
                logger.info(f"📱 Reset SMS sent to {user.phone}")

            return "If an account exists, a reset code has been sent."

        except Exception as e:
            logger.error(f"❌ Password Request Error: {e}")
            raise Exception("Service unavailable.")

    @staticmethod
    async def confirm_reset_async(data):
        """
        Verifies token/OTP and resets password.
        Accepts dictionary/object with: uidb64/token OR phone/otp, and new_password.
        """
        try:
            user = None
            
            # 1. Resolve User
            if 'uidb64' in data and data['uidb64']:
                # Email Flow
                try:
                    uid = force_str(urlsafe_base64_decode(data['uidb64']))
                    user = await UnifiedUser.objects.aget(pk=uid)
                except (TypeError, ValueError, OverflowError, UnifiedUser.DoesNotExist):
                    raise Exception("Invalid reset link.")
                
                if not default_token_generator.check_token(user, data['token']):
                    raise Exception("Invalid or expired token.")
            
            elif 'phone' in data and data['phone']:
                # Phone Flow
                user = await UnifiedUser.objects.aget(phone=data['phone'])
                if not OTPService.verify_otp(user.id, data['token'], purpose='password_reset'):
                    raise Exception("Invalid or expired OTP.")
            
            else:
                raise Exception("Invalid request data.")

            # 2. Reset Password
            user.set_password(data['new_password'])
            await user.asave()
            
            # 3. Notification
            if user.email:
                EmailManager.send_mail(
                    subject="Password Changed",
                    recipients=[user.email],
                    template_name="accounts/email/password_changed.html",
                    context={"user": user}
                )
                
            logger.info(f"✅ Password reset successful for User {user.id}")
            return "Password has been reset successfully."

        except Exception as e:
            logger.error(f"❌ Password Confirm Error: {e}")
            raise Exception(str(e))
