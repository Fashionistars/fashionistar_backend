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
    def register_sync(
        email: str = None,
        phone: str = None,
        password: str = None,
        role: str = 'client',
        request: Any = None,
        **extra_fields
    ) -> Dict[str, Any]:
        """
        Synchronous User Registration Flow (DRF/Classic).

        Orchestrates the full registration pipeline inside a single
        atomic transaction, mirroring the legacy ``RegisterViewCelery``
        pattern line-by-line:

        1. Atomic Database Transaction (rollback on ANY failure)
        2. User Creation via ``CustomUserManager.create_user``
        3. OTP Generation via ``OTPService.generate_otp_sync``
        4. Email / SMS Dispatch via ``EmailManager`` / ``SMSManager``

        Args:
            email (str, optional): User's email address.
            phone (str, optional): User's phone number (E.164 format).
            password (str): Plain-text password (hashed internally).
            role (str): RBAC role — 'vendor' or 'client'. Defaults to 'client'.
            request (Any, optional): The originating HTTP request (for audit).
            **extra_fields: Additional model fields (first_name, etc.).

        Returns:
            Dict[str, Any]: Dictionary containing:
                - message (str): Human-readable success message.
                - user_id (int): Primary key of the created user.
                - email (str | None): User's email if provided.
                - phone (str | None): User's phone if provided.

        Raises:
            Exception: Re-raises any exception after logging and
                       triggering transaction rollback.
        """
        try:
            with transaction.atomic():
                # ── Sanitize: Strip validation-only / non-model fields ───
                for key in ('password_confirm', 'password2',
                            'password_confirmation'):
                    extra_fields.pop(key, None)

                # ── Auto-detect auth_provider from identifier ────────────
                if email:
                    extra_fields.setdefault('auth_provider', 'email')
                elif phone:
                    extra_fields.setdefault('auth_provider', 'phone')

                # ── 1. Create User (via CustomUserManager) ───────────────
                user = UnifiedUser.objects.create_user(
                    email=email,
                    phone=phone,
                    password=password,
                    role=role,
                    is_active=False,
                    is_verified=False,
                    **extra_fields
                )
                logger.info(
                    f"✅ User created (Sync): "
                    f"identifier={email or phone}, "
                    f"id={user.id}, role={role}, "
                    f"provider={user.auth_provider}"
                )

                # ── 2. Generate OTP ──────────────────────────────────────
                otp = OTPService.generate_otp_sync(
                    user.id, purpose='verify'
                )

                # ── 3. Send Notification (Email or SMS) ──────────────────
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
                    logger.warning(
                        f"⚠️ User {user.id} created without "
                        f"Email or Phone — no OTP dispatched"
                    )

                return {
                    'message': (
                        'Registration successful. '
                        'Check email/phone for OTP.'
                    ),
                    'user_id': user.id,
                    'email': email,
                    'phone': str(phone) if phone else None
                }

        except Exception as e:
            # ── Explicit rollback (matches legacy pattern) ───────────────
            transaction.set_rollback(True)
            logger.error(
                f"❌ Registration Failed (Sync): {str(e)}",
                exc_info=True
            )
            raise

    @staticmethod
    async def register_async(email: str = None, phone: str = None,
                            password: str = None, role: str = 'client',
                            request: Any = None, **extra_fields) -> Dict[str, Any]:
        """
        Asynchronous User Registration Flow (Ninja/ASGI).
        Wraps synchronous method to ensure transaction atomicity.
        """
        try:
            return await sync_to_async(RegistrationService.register_sync)(
                email=email,
                phone=phone,
                password=password,
                role=role,
                request=request,
                **extra_fields
            )

        except Exception as e:
            logger.error(f"❌ Registration Failed (Async Wrapper): {str(e)}", exc_info=True)
            raise e
