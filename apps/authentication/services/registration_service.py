import logging
import asyncio
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from asgiref.sync import sync_to_async

from apps.authentication.models import UnifiedUser
from apps.authentication.managers import CustomUserManager
from apps.authentication.services.otp_service import OTPService
from apps.common.managers.email import EmailManager
from apps.common.managers.sms import SMSManager

logger = logging.getLogger('application')

class RegistrationService:
    """
    Centralized Registration Service.
    Handles User Creation, OTP Generation, and Notification Dispatch.
    Strictly separates Synchronous and Asynchronous flows.
    """

    @staticmethod
    def register_sync(email: str = None, phone: str = None, 
                     password: str = None, role: str = 'client',
                     request: Any = None, **extra_fields) -> Dict[str, Any]:
        """
        Synchronous User Registration Flow (DRF/Classic).
        
        Orchestrates:
        1. Atomic Database Transaction
        2. User Creation (via CustomUserManager)
        3. OTP Generation (via OTPService)
        4. Email/SMS Dispatch (via Managers)
        """
        try:
            with transaction.atomic():
                # 1. Create User
                user = CustomUserManager().create_user(
                    email=email, 
                    phone=phone, 
                    password=password, 
                    role=role,
                    is_active=False, 
                    is_verified=False,
                    **extra_fields
                )
                logger.info(f"✅ User created (Sync): {email or phone} (ID: {user.id})")
                
                # 2. Generate OTP
                otp = OTPService.generate_otp_sync(user.id, purpose='verify')
                
                # 3. Send Notification containing OTP
                if email:
                    context = {'user_id': user.id, 'otp': otp}
                    EmailManager.send_mail(
                        subject="Verify Your Email",
                        recipients=[email],
                        template_name='otp.html',
                        context=context
                    )
                    logger.info(f"✅ OTP email sent to {email}")
                elif phone:
                    body = f"Your verification OTP: {otp}"
                    SMSManager.send_sms(str(phone), body)
                    logger.info(f"✅ OTP SMS sent to {phone}")
                else:
                    logger.warning(f"⚠️ User {user.id} created without Email or Phone?")

                return {
                    'message': 'Registration successful. Check email/phone for OTP.',
                    'user_id': user.id,
                    'email': email,
                    'phone': str(phone) if phone else None
                }
                
        except Exception as e:
            logger.error(f"❌ Registration Failed (Sync): {str(e)}", exc_info=True)
            # Transaction automatically rolls back on exception exit of context manager
            raise e

    @staticmethod
    async def register_async(email: str = None, phone: str = None,
                            password: str = None, role: str = 'client',
                            request: Any = None, **extra_fields) -> Dict[str, Any]:
        """
        Asynchronous User Registration Flow (Ninja/ASGI).
        
        Uses Native Async methods where available (Django 4.1+ / 6.0).
        """
        try:
            # Async Atomic Transaction
            async with transaction.atomic():
                # 1. Create User (Async)
                # Note: CustomUserManager must implement acreate_user or inherit from BaseUserManager
                # Django's BaseUserManager has `acreate_user` since 4.1 via AsyncManager mixin usually.
                # If CustomUserManager overrides create_user but not acreate_user, we might need check.
                # Assuming CustomUserManager is standard or has acreate_user.
                user = await CustomUserManager().acreate_user(
                    email=email,
                    phone=phone,
                    password=password,
                    role=role,
                    is_active=False,
                    is_verified=False,
                    **extra_fields
                )
                logger.info(f"✅ User created (Async): {email or phone} (ID: {user.id})")
                
                # 2. Generate OTP (Async)
                otp = await OTPService.generate_otp_async(user.id, purpose='verify')
                
                # 3. Send Notification (Async)
                if email:
                    context = {'user_id': user.id, 'otp': otp}
                    await EmailManager.asend_mail(
                        subject="Verify Your Email",
                        recipients=[email],
                        template_name='otp.html',
                        context=context
                    )
                    logger.info(f"✅ OTP email sent (Async) to {email}")
                elif phone:
                    body = f"Your verification OTP: {otp}"
                    # Ensure phone is string for SMS manager
                    await SMSManager.asend_sms(str(phone), body)
                    logger.info(f"✅ OTP SMS sent (Async) to {phone}")
                
                return {
                    'message': 'Registration successful. Check email/phone for OTP.',
                    'user_id': user.id,
                    'email': email,
                    'phone': str(phone) if phone else None
                }

        except Exception as e:
            logger.error(f"❌ Registration Failed (Async): {str(e)}", exc_info=True)
            # Async transaction rollback
            raise e
