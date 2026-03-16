# apps/authentication/services/registration/sync_service.py
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
from apps.authentication.services.otp import OTPService
from apps.common.events import event_bus  # EventBus singleton

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
            2. generate OTP (stored in Redis)
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
                    if hasattr(exc, 'message_dict'):
                        raise drf_serializers.ValidationError(exc.message_dict)
                    raise drf_serializers.ValidationError({'error': exc.messages})
                except IntegrityError as exc:
                    err_str = str(exc).lower()
                    if 'email' in err_str:
                        raise drf_serializers.ValidationError(
                            {'email': ['A user with this email address already exists.']}
                        )
                    if 'phone' in err_str:
                        raise drf_serializers.ValidationError(
                            {'phone': ['A user with this phone number already exists.']}
                        )
                    raise drf_serializers.ValidationError(
                        {'error': ['A user with these details already exists.']}
                    )

                logger.info(
                    "✅ User created (sync): id=%s identifier=%s role=%s",
                    user.id, email or phone, role
                )

                # ── 2. GENERATE OTP (stored in Redis, atomic) ─────────────
                otp = OTPService.generate_otp_sync(user.id, purpose='verify')
                logger.info("🔐 OTP generated for user_id=%s", user.id)

            # ── 3. EMIT 'user.registered' EVENT (replaces Django signal) ──
            # emit_on_commit() fires ONLY after the transaction commits.
            # The handler (apps.common.event_handlers.on_user_registered)
            # dispatches the Celery task upsert_user_lifecycle_registry.
            event_bus.emit_on_commit(
                'user.registered',
                user_uuid=str(user.id),
                email=str(user.email) if user.email else None,
                phone=str(user.phone) if user.phone else None,
                member_id=str(user.member_id) if user.member_id else '',
                role=str(user.role) if user.role else '',
                auth_provider=str(user.auth_provider) if user.auth_provider else 'email',
                country=str(user.country) if user.country else None,
                state=str(user.state) if user.state else None,
                city=str(user.city) if user.city else None,
            )
            logger.info(
                "📡 EventBus: 'user.registered' scheduled on_commit [user_id=%s]",
                str(user.id),
            )

            # ── 4. FIRE OTP CELERY TASK via transaction.on_commit() ──────
            # on_commit() fires ONLY after the outermost transaction commits
            # successfully — ensuring the user row is visible to the worker.
            _user_id = str(user.id)
            _otp = otp

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
                    'SITE_URL': getattr(_settings, 'SITE_URL', 'https://fashionistar.io'),
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
                'email': email,
                'phone': phone,
            }

        except Exception as exc:
            logger.error(
                "❌ RegistrationService.register_sync failed: %s", str(exc),
                exc_info=True
            )
            raise
