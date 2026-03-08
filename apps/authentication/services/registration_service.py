# apps/authentication/services/registration_service.py
"""
FASHIONISTAR — Registration Service (Sync + Async)
===================================================
Orchestrates the full user registration pipeline:

  1. Atomic DB transaction → UnifiedUser creation
  2. OTP generation via OTPService
  3. Email / SMS dispatch via Celery background task (NON-BLOCKING)
     → send_email_task.delay()  ← Immediate Redis-queued background job
     → send_sms_task.delay()    ← Same

WHY CELERY:
  Sending SMTP email synchronously inside a request would:
  - Block the request thread for 200-2000 ms (SMTP round-trip)
  - Fail the whole registration if the email server is slow/down
  - Prevent scaling beyond ~5-10 RPS on a single WSGI worker

  With Celery + Redis:
  - Request completes in <50 ms (DB write only)
  - Email fires <100 ms later in a background worker
  - SMTP failures → automatic 3-retry with exponential backoff
  - Monitoring via Flower dashboard

Architecture:
    RegisterView.create()
        → perform_create()
        → RegistrationService.register_sync()
            ├── UnifiedUser.objects.create_user()       [atomic]
            ├── OTPService.generate_otp_sync()          [atomic]
            └── send_email_task.delay() OR              [Celery async → Redis]
                send_sms_task.delay()
"""

import logging
from typing import Dict, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp_service import OTPService

logger = logging.getLogger(__name__)


class RegistrationService:
    """
    Centralised Registration Service.
    Strictly separates sync and async flows.
    Both flows fire OTP notifications via Celery background tasks.
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
        Synchronous (WSGI/DRF) User Registration.

        Completes in <50ms (DB only). OTP email/SMS fired via
        Celery task (.delay()) — non-blocking.

        Steps:
            1. atomic transaction: create user
            2. generate OTP (stored in DB)
            3. .delay() → Celery task → Redis queue → worker sends email/SMS
            4. return 201 payload to client

        Args:
            email     : User email address (optional if phone provided).
            phone     : User phone E.164 (optional if email provided).
            password  : Plain-text password → hashed inside create_user().
            role      : 'vendor' or 'client'.
            request   : Originating HttpRequest (for audit log). Optional.
            **extra_fields : Any additional UnifiedUser field values.

        Returns:
            Dict with: message, user_id, email, phone
        """
        # ── Lazily import Celery tasks to avoid circular imports ──────────
        from apps.authentication.tasks import send_email_task, send_sms_task

        try:
            with transaction.atomic():
                # ── Strip validation-only fields (not stored on model) ────
                for key in ('password_confirm', 'password2', 'password_confirmation'):
                    extra_fields.pop(key, None)

                # ── Auto-detect auth_provider ─────────────────────────────
                if email:
                    extra_fields.setdefault('auth_provider', 'email')
                elif phone:
                    extra_fields.setdefault('auth_provider', 'phone')

                # ── 1. CREATE USER (atomic) ────────────────────────────────
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
                    "✅ User created (sync): id=%s identifier=%s role=%s",
                    user.id, email or phone, role
                )

                # ── 2. GENERATE OTP (stored in DB, atomic) ────────────────
                otp = OTPService.generate_otp_sync(user.id, purpose='verify')
                logger.info(
                    "🔐 OTP generated for user_id=%s", user.id
                )

            # ── 3. FIRE CELERY TASK (outside atomic block) ────────────────
            # The .delay() call puts the job on the Redis queue immediately.
            # The Celery worker picks it up and sends the email/SMS
            # within milliseconds, WITHOUT blocking the HTTP response.
            if email:
                context = {
                    'user_id': str(user.id),
                    'otp': otp,
                    'user_name': getattr(user, 'first_name', None) or email.split('@')[0],
                    'support_email': 'support@fashionistar.io',
                }
                send_email_task.delay(
                    subject="🔐 Verify Your Fashionistar Account",
                    recipients=[email],
                    template_name='authentication/email/registration_email.html',
                    context=context,
                )
                logger.info(
                    "📧 OTP email task queued → Celery [user_id=%s, email=%s]",
                    user.id, email
                )

            elif phone:
                body = (
                    f"Welcome to Fashionistar!\n"
                    f"Your verification OTP is: {otp}\n"
                    f"Valid for 10 minutes. Do not share this code."
                )
                send_sms_task.delay(to=str(phone), body=body)
                logger.info(
                    "📱 OTP SMS task queued → Celery [user_id=%s, phone=%s]",
                    user.id, phone
                )

            else:
                logger.warning(
                    "⚠️ User %s created without email or phone — no OTP dispatched",
                    user.id
                )

            return {
                'message': (
                    'Registration successful. '
                    'Check your email or phone for your OTP verification code.'
                ),
                'user_id': str(user.id),
                'email': email,
                'phone': str(phone) if phone else None,
            }

        except Exception as exc:
            logger.error(
                "❌ RegistrationService.register_sync failed: %s", str(exc),
                exc_info=True
            )
            raise

    # ─────────────────────────────────────────────────────────────────────────
    #  ASYNC WRAPPER (for Ninja / ASGI views)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def register_async(
        email: str = None,
        phone: str = None,
        password: str = None,
        role: str = 'client',
        request: Any = None,
        **extra_fields
    ) -> Dict[str, Any]:
        """
        Async wrapper around register_sync for Django Ninja / ASGI endpoints.
        Celery .delay() is I/O-safe (just drops a message to Redis) so no
        special async handling is needed.
        """
        from asgiref.sync import sync_to_async
        try:
            return await sync_to_async(RegistrationService.register_sync)(
                email=email,
                phone=phone,
                password=password,
                role=role,
                request=request,
                **extra_fields
            )
        except Exception as exc:
            logger.error(
                "❌ RegistrationService.register_async failed: %s", str(exc),
                exc_info=True
            )
            raise
