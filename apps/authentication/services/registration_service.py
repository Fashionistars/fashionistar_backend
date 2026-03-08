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

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from rest_framework import serializers as drf_serializers

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

        # ── Defence-in-depth: Normalise empty strings → None ─────────────
        # The serializer already does this, but we guard here too in case
        # register_sync() is called directly (e.g. from admin commands,
        # management scripts, or async wrappers).
        email = email or None
        phone = str(phone) if phone else None  # PhoneNumber object → str

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
                try:
                    user = UnifiedUser.objects.create_user(
                        email=email,
                        phone=phone,
                        password=password,
                        role=role,
                        is_active=False,
                        is_verified=False,
                        **extra_fields
                    )
                except DjangoValidationError as exc:
                    # model.full_clean() fires on save() — catches race-condition
                    # duplicates that slipped past serializer uniqueness check.
                    # Re-raise as DRF ValidationError so the view returns 400.
                    if hasattr(exc, 'message_dict'):
                        raise drf_serializers.ValidationError(exc.message_dict)
                    raise drf_serializers.ValidationError(
                        {'error': exc.messages}
                    )
                except IntegrityError as exc:
                    # ── DB-level unique constraint fired (bypassed full_clean)
                    # This happens on Uvicorn/ASGI because the ASGI event loop
                    # can interleave coroutines — full_clean() runs OK but
                    # between clean() and save() another request inserts the row.
                    # Also happens when create_user() is called without full_clean
                    # in some edge paths.
                    # Convert to a DRF 400 with a field-specific error message.
                    err_str = str(exc).lower()
                    if 'email' in err_str:
                        raise drf_serializers.ValidationError(
                            {'email': [
                                'A user with this email address already exists.'
                            ]}
                        )
                    if 'phone' in err_str:
                        raise drf_serializers.ValidationError(
                            {'phone': [
                                'A user with this phone number already exists.'
                            ]}
                        )
                    # Unknown constraint — generic 400 (better than 500)
                    raise drf_serializers.ValidationError(
                        {'error': [
                            'A user with these details already exists.'
                        ]}
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

            # ── 3. FIRE CELERY TASK via transaction.on_commit() ───────────
            # WHY on_commit():
            #   .delay() puts a message on the Redis queue immediately.
            #   If called *inside* atomic() (or any outer atomic), the DB
            #   row may not yet be visible to the Celery worker when it
            #   tries to load the user — especially on Uvicorn (ASGI) where
            #   the event loop may interleave coroutines between the DB write
            #   and the Redis publish.
            #
            #   transaction.on_commit() fires the closure ONLY after the
            #   outermost transaction commits successfully.  If the atomic
            #   block rolls back (duplicate, constraint, etc.) the task is
            #   never queued — correct behaviour.
            #
            #   This is the Django-recommended enterprise pattern for
            #   coupling async side-effects to DB transactions.

            _user_id  = str(user.id)   # capture before closure
            _otp      = otp

            if email:
                from django.conf import settings as _settings
                _email_context = {
                    'user_id': _user_id,
                    'otp': _otp,
                    'user_name': (
                        getattr(user, 'first_name', None)
                        or email.split('@')[0]
                    ),
                    'support_email': 'support@fashionistar.io',
                    'SITE_URL': getattr(
                        _settings, 'SITE_URL', 'https://fashionistar.io'
                    ),
                }
                transaction.on_commit(lambda: send_email_task.delay(
                    subject="🔐 Verify Your Fashionistar Account",
                    recipients=[email],
                    template_name='authentication/email/registration_email.html',
                    context=_email_context,
                ))
                logger.info(
                    "📧 OTP email task scheduled on_commit → Celery "
                    "[user_id=%s email=%s]",
                    _user_id, email,
                )

            elif phone:
                _phone_body = (
                    f"Welcome to Fashionistar!\n"
                    f"Your verification OTP is: {_otp}\n"
                    f"Valid for 10 minutes. Do not share this code."
                )
                transaction.on_commit(lambda: send_sms_task.delay(
                    to=phone, body=_phone_body
                ))
                logger.info(
                    "📱 OTP SMS task scheduled on_commit → Celery "
                    "[user_id=%s phone=%s]",
                    _user_id, phone,
                )

            else:
                logger.warning(
                    "⚠️ User %s created without email or phone — no OTP dispatched",
                    _user_id,
                )

            return {
                'message': (
                    'Registration successful. '
                    'Check your email or phone for your OTP verification code.'
                ),
                'user_id': _user_id,
                'email': email,          # None for phone-only users
                'phone': phone,          # None for email-only users (already str or None)
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
