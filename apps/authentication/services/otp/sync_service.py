# apps/authentication/services/otp/sync_service.py
"""
FASHIONISTAR — OTP Service (Sync + Async)
==========================================
Centralized OTP Management Service.

Handles:
  - Generation  : generate_numeric_otp() → encrypt → store in Redis (TTL: 5 min)
  - Verification: scan Redis for otp:{user_id}:{purpose}:* → decrypt → compare → delete
  - Resend      : invalidate old OTPs → generate new → dispatch via Email/SMS

Redis key pattern: otp:{user_id}:{purpose}:{encrypted_snippet}
  Allows O(1) prefix scan per user without full keyspace scan.
"""

import logging
from typing import Any
from asgiref.sync import sync_to_async

from apps.common.utils import (
    get_redis_connection_safe,
    generate_numeric_otp,
    encrypt_otp,
    decrypt_otp,
)
from apps.authentication.models import UnifiedUser

logger = logging.getLogger(__name__)


class OTPService:
    """
    Centralised OTP Management Service.
    Handles Generation, Storage (Redis), Encryption, and Verification.
    Supports both Synchronous and Asynchronous execution.
    """

    # ------------------------------------------------------------------
    # GENERATE
    # ------------------------------------------------------------------

    @staticmethod
    def generate_otp_sync(user_id: Any, purpose: str = 'verify') -> str:
        """
        Generates, encrypts, and stores an OTP in Redis (Synchronous).

        Args:
            user_id (UUID/int/str): The user's primary key.
            purpose (str): Context — 'verify', 'reset', 'login'.

        Returns:
            str: Plain-text OTP to send via Email/SMS.

        Raises:
            Exception: If Redis is unavailable.
        """
        try:
            otp = generate_numeric_otp()
            encrypted_otp = encrypt_otp(otp)

            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error("Redis unavailable for OTP generation (User: %s)", user_id)
                raise Exception("Service unavailable")

            # Key: otp:{user_id}:{purpose}:{snippet}
            # Snippet allows per-purpose prefix scan without full keyspace scan.
            snippet = encrypted_otp[:16]
            redis_key = f"otp:{user_id}:{purpose}:{snippet}"

            # Value: full encrypted OTP (used by verify_otp_sync to decrypt + compare)
            redis_conn.setex(redis_key, 300, encrypted_otp)  # TTL: 5 minutes

            logger.info("OTP generated for User %s (Purpose: %s)", user_id, purpose)
            return otp

        except Exception as exc:
            logger.error("OTP Generation Failed: %s", exc, exc_info=True)
            raise

    @staticmethod
    async def generate_otp_async(user_id: Any, purpose: str = 'verify') -> str:
        """Async wrapper — wraps generate_otp_sync in sync_to_async."""
        return await sync_to_async(OTPService.generate_otp_sync)(user_id, purpose)

    # ------------------------------------------------------------------
    # VERIFY
    # ------------------------------------------------------------------

    @staticmethod
    def verify_otp_sync(user_id: Any, otp: str, purpose: str = 'verify') -> bool:
        """
        Verifies an OTP (Synchronous).

        Strategy:
          1. Scan Redis for keys matching otp:{user_id}:{purpose}:*
          2. For each key: get value → decrypt → compare
          3. On match: delete key (one-time use) → return True
          4. If no match found: return False

        Args:
            user_id: User's primary key.
            otp    : Plain-text OTP submitted by the user.
            purpose: Must match the purpose used at generation time.

        Returns:
            bool: True if verified and deleted, False otherwise.
        """
        try:
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                raise Exception("Service unavailable")

            pattern = f"otp:{user_id}:{purpose}:*"
            keys = redis_conn.keys(pattern)

            for key in keys:
                stored_encrypted = redis_conn.get(key)
                if not stored_encrypted:
                    continue

                decrypted = decrypt_otp(stored_encrypted.decode())
                if decrypted == str(otp):
                    redis_conn.delete(key)
                    logger.info(
                        "OTP Verified for User %s (Purpose: %s)", user_id, purpose
                    )
                    return True

            logger.warning(
                "OTP Verification Failed for User %s (Purpose: %s)", user_id, purpose
            )
            return False

        except Exception as exc:
            logger.error("OTP Verification Error: %s", exc, exc_info=True)
            return False

    @staticmethod
    async def verify_otp_async(user_id: Any, otp: str, purpose: str = 'verify') -> bool:
        """Async wrapper — wraps verify_otp_sync in sync_to_async."""
        return await sync_to_async(OTPService.verify_otp_sync)(user_id, otp, purpose)

    # ------------------------------------------------------------------
    # RESEND
    # ------------------------------------------------------------------

    @staticmethod
    def resend_otp_sync(email_or_phone: str, purpose: str = 'verify') -> str:
        """
        Resends an OTP to the user — invalidates previous ones (Synchronous).

        Security note: Returns a generic message regardless of whether the
        user exists to prevent account enumeration attacks.

        Args:
            email_or_phone: Registered email or phone number.
            purpose       : OTP purpose — matches generation purpose.

        Returns:
            str: Generic non-enumerable success message.
        """
        # Lazily import tasks to avoid circular imports
        from apps.authentication.tasks import send_email_task, send_sms_task
        from django.db import transaction

        try:
            # 1. Find User
            if '@' in email_or_phone:
                user = UnifiedUser.objects.filter(email=email_or_phone).first()
            else:
                user = UnifiedUser.objects.filter(phone=email_or_phone).first()

            if not user:
                # Generic message to prevent user enumeration
                logger.warning(
                    "Resend OTP requested for non-existent user: %s", email_or_phone
                )
                return "If an account exists, a new OTP has been sent."

            # 2. Invalidate Old OTPs for this purpose
            redis_conn = get_redis_connection_safe()
            if redis_conn:
                pattern = f"otp:{user.id}:{purpose}:*"
                old_keys = redis_conn.keys(pattern)
                if old_keys:
                    redis_conn.delete(*old_keys)
                    logger.info(
                        "Invalidated %d old OTP(s) for user %s (Purpose: %s)",
                        len(old_keys), user.id, purpose
                    )

            # 3. Generate New OTP
            otp = OTPService.generate_otp_sync(user.id, purpose)

            # 4. Dispatch via Celery (non-blocking, fires after transaction commit)
            _user_id = str(user.id)
            _otp = otp

            if user.email:
                from django.conf import settings as _settings
                _email_context = {
                    'user_id': _user_id,
                    'otp': _otp,
                    'user_name': (
                        getattr(user, 'first_name', None)
                        or user.email.split('@')[0]
                    ),
                    'support_email': 'support@fashionistar.io',
                    'SITE_URL': getattr(_settings, 'SITE_URL', 'https://fashionistar.io'),
                }
                transaction.on_commit(lambda: send_email_task.delay(
                    subject="🔐 Your New Fashionistar Verification OTP",
                    recipients=[user.email],
                    template_name='authentication/email/otp_resend_email.html',
                    context=_email_context,
                ))
                logger.info(
                    "📧 OTP resend email scheduled on_commit → Celery "
                    "[user_id=%s email=%s]",
                    _user_id, user.email,
                )

            elif user.phone:
                _phone_body = (
                    f"Your new Fashionistar verification OTP: {_otp}\n"
                    f"Valid for 10 minutes. Do not share this code."
                )
                transaction.on_commit(lambda: send_sms_task.delay(
                    to=str(user.phone), body=_phone_body
                ))
                logger.info(
                    "📱 OTP resend SMS scheduled on_commit → Celery "
                    "[user_id=%s phone=%s]",
                    _user_id, str(user.phone),
                )

            return "If an account exists, a new OTP has been sent."

        except Exception as exc:
            logger.error("Resend OTP Error: %s", exc, exc_info=True)
            raise

    @staticmethod
    async def resend_otp_async(email_or_phone: str, purpose: str = 'verify') -> str:
        """Async wrapper — wraps resend_otp_sync in sync_to_async."""
        try:
            if '@' in email_or_phone:
                user = await UnifiedUser.objects.filter(email=email_or_phone).afirst()
            else:
                user = await UnifiedUser.objects.filter(phone=email_or_phone).afirst()

            if not user:
                logger.warning(
                    "Resend OTP requested (Async) for non-existent: %s", email_or_phone
                )
                return "If an account exists, a new OTP has been sent."

            # Invalidate old OTPs
            redis_conn = get_redis_connection_safe()
            if redis_conn:
                pattern = f"otp:{user.id}:{purpose}:*"
                old_keys = await sync_to_async(redis_conn.keys)(pattern)
                if old_keys:
                    await sync_to_async(redis_conn.delete)(*old_keys)

            # Generate + dispatch (async wrappers)
            otp = await OTPService.generate_otp_async(user.id, purpose)

            from apps.authentication.tasks import send_email_task, send_sms_task
            from django.conf import settings as _settings

            if user.email:
                _email_context = {
                    'user_id': str(user.id),
                    'otp': otp,
                    'user_name': getattr(user, 'first_name', None) or user.email.split('@')[0],
                    'support_email': 'support@fashionistar.io',
                    'SITE_URL': getattr(_settings, 'SITE_URL', 'https://fashionistar.io'),
                }
                send_email_task.delay(
                    subject="🔐 Your New Fashionistar Verification OTP",
                    recipients=[user.email],
                    template_name='authentication/email/otp_resend_email.html',
                    context=_email_context,
                )
            elif user.phone:
                _phone_body = (
                    f"Your new Fashionistar verification OTP: {otp}\n"
                    f"Valid for 10 minutes. Do not share this code."
                )
                send_sms_task.delay(to=str(user.phone), body=_phone_body)

            return "If an account exists, a new OTP has been sent."

        except Exception as exc:
            logger.error("Resend OTP Async Error: %s", exc, exc_info=True)
            raise
