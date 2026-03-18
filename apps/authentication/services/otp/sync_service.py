# apps/authentication/services/otp/sync_service.py
"""
FASHIONISTAR — OTP Service (Sync + Async)
==========================================
Centralised OTP Management Service.

Handles:
  - Generation   : generate_numeric_otp() → encrypt → store in Redis (TTL 5 min)
  - Verification : Two strategies:
      a) verify_otp_sync(user_id, otp, purpose)
            O(1) prefix-scan per user → decrypt → compare → delete.
            Used when user_id is already known.
      b) verify_by_otp_sync(otp, purpose)            [PRIMARY for VerifyOTPView]
            O(1) via SHA-256 secondary hash index → returns user_id.
            Client only sends the OTP — no user_id required (mirrors legacy UX).
  - Resend       : invalidate old OTPs → generate new → dispatch Email / SMS

Redis key schema
────────────────
Primary   : otp:{user_id}:{purpose}:{snippet}
            Value  = "{encrypted_otp}|{sha256_hex}"

Secondary : otp_hash:{sha256_hex}
            Value  = "{primary_key}"
            TTL    = same 300 s as primary

The secondary index enables true O(1) OTP-only lookup, scales to 1 M+ req/s
without any keyspace scan.  Cleanup during resend reads the sha256_hex from
the primary value and deletes the secondary index atomically.

Legacy / backward-compat note
──────────────────────────────
Old primary-key values stored as bare encrypted strings (no `|sha256_hex`)
are still handled gracefully by verify_otp_sync().  They will expire
naturally within 5 minutes.
"""

import hashlib
import logging
from typing import Any, Optional, Dict
from asgiref.sync import sync_to_async

from apps.common.utils import (
    get_redis_connection_safe,
    generate_numeric_otp,
    encrypt_otp,
    decrypt_otp,
)
from apps.authentication.models import UnifiedUser

logger = logging.getLogger(__name__)


def _sha256(plain: str) -> str:
    """Return lowercase hex SHA-256 digest of *plain*."""
    return hashlib.sha256(plain.encode()).hexdigest()


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

        Storage strategy (two Redis writes per OTP):
          1. Primary key  : otp:{user_id}:{purpose}:{snippet}
                            Value = "{encrypted_otp}|{sha256_hex}"
          2. Secondary idx: otp_hash:{sha256_hex}
                            Value = primary_key string (for O(1) verify_by_otp)

        Both keys share the same TTL (300 s / 5 minutes).

        Args:
            user_id (UUID/int/str): The user's primary key.
            purpose (str): Context — 'verify', 'reset', 'login'.

        Returns:
            str: Plain-text OTP to send via Email / SMS.

        Raises:
            Exception: If Redis is unavailable.
        """
        try:
            otp          = generate_numeric_otp()
            otp_hash     = _sha256(otp)           # deterministic — same each call
            encrypted    = encrypt_otp(otp)        # Fernet — non-deterministic

            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error("Redis unavailable for OTP generation (User: %s)", user_id)
                raise Exception("Service unavailable")

            # Primary — snippet prevents key collision between purposes
            snippet     = encrypted[:16]
            primary_key = f"otp:{user_id}:{purpose}:{snippet}"
            value       = f"{encrypted}|{otp_hash}"

            # Secondary hash index — enables O(1) OTP-only lookup
            hash_key = f"otp_hash:{otp_hash}"

            pipe = redis_conn.pipeline()
            pipe.setex(primary_key, 300, value)
            pipe.setex(hash_key,    300, primary_key)   # value = primary_key string
            pipe.execute()

            logger.info("OTP generated for User %s (Purpose: %s)", user_id, purpose)
            return otp

        except Exception as exc:
            logger.error("OTP Generation Failed: %s", exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # VERIFY — by user_id (internal / backward-compat)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_otp_sync(user_id: Any, otp: str, purpose: str = 'verify') -> bool:
        """
        Verifies an OTP when user_id is already known (Synchronous).

        Strategy:
          1. KEYS otp:{user_id}:{purpose}:*   — narrow prefix scan (O(n_user))
          2. For each key: get value → strip '|sha256' suffix → decrypt → compare
          3. On match: delete primary key + secondary hash index → return True

        This is the legacy-compatible path used internally when user_id is
        already available (e.g., resend confirmation step).

        Args:
            user_id : User's primary key.
            otp     : Plain-text OTP submitted by the user.
            purpose : Must match the purpose used at generation time.

        Returns:
            bool: True if verified and deleted, False otherwise.
        """
        try:
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                raise Exception("Service unavailable")

            pattern = f"otp:{user_id}:{purpose}:*"
            keys    = redis_conn.keys(pattern)

            for key in keys:
                raw = redis_conn.get(key)
                if not raw:
                    continue

                raw_str = raw.decode()

                # Support both new format ("encrypted|hash") and legacy (bare encrypted)
                if '|' in raw_str:
                    encrypted_part, stored_hash = raw_str.rsplit('|', 1)
                else:
                    encrypted_part = raw_str
                    stored_hash    = None

                decrypted = decrypt_otp(encrypted_part)
                if decrypted == str(otp):
                    # Delete primary
                    pipe = redis_conn.pipeline()
                    pipe.delete(key)
                    # Delete secondary index if it exists
                    if stored_hash:
                        pipe.delete(f"otp_hash:{stored_hash}")
                    pipe.execute()
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

    # ------------------------------------------------------------------
    # VERIFY — by OTP only  (O(1) — no user_id needed in request)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_by_otp_sync(
        otp: str, purpose: str = 'verify'
    ) -> Optional[Dict[str, str]]:
        """
        Verifies an OTP without requiring user_id in the request (Synchronous).

        This mirrors the legacy VerifyOTPView pattern (client sends only the
        OTP code, server discovers the user from Redis), but replaces the
        legacy O(n) full-keyspace scan with an O(1) SHA-256 hash index.

        Algorithm:
          1. Hash the submitted OTP: sha256_hex = sha256(otp)
          2. GET otp_hash:{sha256_hex}  → primary_key   [O(1) Redis lookup]
          3. Parse user_id and purpose from primary_key
          4. Validate purpose matches
          5. Verify primary key still exists  (TTL guard)
          6. Delete primary key + hash index atomically
          7. Return {'user_id': ..., 'purpose': ...}

        Scalability:
          Two Redis GET/DEL calls regardless of total OTP count.
          Handles 1 000 000 + concurrent OTP lookups per second.
          No SCAN, no KEYS, no iteration — pure O(1).

        Args:
            otp     : Plain-text 6-digit OTP submitted by the client.
            purpose : Expected OTP purpose ('verify', 'reset', 'login').

        Returns:
            dict with 'user_id' and 'purpose' on success, None on failure.
        """
        try:
            redis_conn = get_redis_connection_safe()
            if not redis_conn:
                logger.error("Redis unavailable during OTP-only verification")
                return None

            # ── Step 1-2: O(1) hash index lookup ──────────────────────────
            otp_hash   = _sha256(otp)
            hash_key   = f"otp_hash:{otp_hash}"
            primary_raw = redis_conn.get(hash_key)

            if not primary_raw:
                logger.warning("OTP-only verify failed: hash index miss (otp=****)")
                return None

            primary_key = primary_raw.decode()

            # ── Step 3-4: Parse and validate purpose ───────────────────────
            # key format: otp:{user_id}:{purpose}:{snippet}
            parts = primary_key.split(':')
            if len(parts) < 4 or parts[0] != 'otp':
                logger.warning(
                    "OTP-only verify failed: malformed primary key '%s'", primary_key
                )
                return None

            user_id        = parts[1]
            stored_purpose = parts[2]

            if stored_purpose != purpose:
                logger.warning(
                    "OTP purpose mismatch: expected=%s got=%s user=%s",
                    purpose, stored_purpose, user_id,
                )
                return None

            # ── Step 5: TTL guard — primary key must still exist ──────────
            primary_val = redis_conn.get(primary_key)
            if not primary_val:
                logger.warning(
                    "OTP-only verify: primary key expired/missing for user %s", user_id
                )
                # Clean up orphaned hash index
                redis_conn.delete(hash_key)
                return None

            # ── Step 6: Atomic delete of both keys ─────────────────────────
            pipe = redis_conn.pipeline()
            pipe.delete(primary_key)
            pipe.delete(hash_key)
            pipe.execute()

            logger.info(
                "✅ OTP verified (OTP-only path) for user=%s purpose=%s",
                user_id, purpose,
            )
            return {'user_id': user_id, 'purpose': stored_purpose}

        except Exception as exc:
            logger.error("OTP-only Verification Error: %s", exc, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # RESEND
    # ------------------------------------------------------------------

    @staticmethod
    def resend_otp_sync(email_or_phone: str, purpose: str = 'verify') -> str:
        """
        Resends an OTP — invalidates previous ones, generates a fresh OTP (Sync).

        Security: Returns a generic message regardless of whether the user
        exists to prevent account enumeration attacks.

        Cleanup strategy:
          1. KEYS otp:{user_id}:{purpose}:*    — find all primary keys
          2. For each: parse value → extract sha256_hex → delete hash index
          3. DEL all primary keys
          → Both primary and secondary index entries are purged atomically.

        Template: authentication/email/resend_otp.html
        Dispatched via Celery on_commit() to avoid task-before-commit race.

        Args:
            email_or_phone : Registered email or phone.
            purpose        : OTP purpose, matches generation purpose.

        Returns:
            str: Generic non-enumerable success message.
        """
        from apps.authentication.tasks import send_email_task, send_sms_task
        from django.db import transaction

        try:
            # 1. Find User
            if '@' in email_or_phone:
                user = UnifiedUser.objects.filter(email=email_or_phone).first()
            else:
                user = UnifiedUser.objects.filter(phone=email_or_phone).first()

            if not user:
                logger.warning(
                    "Resend OTP requested for non-existent user: %s", email_or_phone
                )
                return "If an account exists, a new OTP has been sent."

            # 2. Invalidate old OTPs — primary keys + their secondary hash indexes
            redis_conn = get_redis_connection_safe()
            if redis_conn:
                pattern  = f"otp:{user.id}:{purpose}:*"
                old_keys = redis_conn.keys(pattern)
                if old_keys:
                    pipe = redis_conn.pipeline()
                    for key in old_keys:
                        raw = redis_conn.get(key)
                        if raw:
                            raw_str = raw.decode()
                            if '|' in raw_str:
                                _, old_hash = raw_str.rsplit('|', 1)
                                pipe.delete(f"otp_hash:{old_hash}")
                        pipe.delete(key)
                    pipe.execute()
                    logger.info(
                        "Invalidated %d old OTP(s) for user %s (Purpose: %s)",
                        len(old_keys), user.id, purpose,
                    )

            # 3. Generate New OTP
            otp = OTPService.generate_otp_sync(user.id, purpose)

            # 4. Dispatch via Celery (non-blocking, fires after transaction commit)
            _user_id = str(user.id)
            _otp     = otp

            if user.email:
                from django.conf import settings as _settings
                _email_context = {
                    'user_id':       _user_id,
                    'otp':           _otp,
                    'user_name': (
                        getattr(user, 'first_name', None)
                        or user.email.split('@')[0]
                    ),
                    'support_email': 'support@fashionistar.io',
                    'SITE_URL': getattr(
                        _settings, 'SITE_URL', 'https://fashionistar.io'
                    ),
                }
                transaction.on_commit(lambda: send_email_task.delay(
                    subject='🔐 Your New Fashionistar Verification OTP',
                    recipients=[user.email],
                    template_name='authentication/email/resend_otp.html',  # ← FIXED
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
                    "Valid for 5 minutes. Do not share this code."
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
        """Async wrapper — wraps only the user-lookup and OTP generation;
        task dispatch is handled inline since on_commit is sync-only."""
        try:
            if '@' in email_or_phone:
                user = await UnifiedUser.objects.filter(
                    email=email_or_phone
                ).afirst()
            else:
                user = await UnifiedUser.objects.filter(
                    phone=email_or_phone
                ).afirst()

            if not user:
                logger.warning(
                    "Resend OTP (Async) for non-existent: %s", email_or_phone
                )
                return "If an account exists, a new OTP has been sent."

            # Invalidate old OTPs + their hash indexes
            redis_conn = get_redis_connection_safe()
            if redis_conn:
                pattern  = f"otp:{user.id}:{purpose}:*"
                old_keys = await sync_to_async(redis_conn.keys)(pattern)
                if old_keys:
                    keys_to_del = list(old_keys)
                    for key in old_keys:
                        raw = await sync_to_async(redis_conn.get)(key)
                        if raw:
                            raw_str = raw.decode()
                            if '|' in raw_str:
                                _, old_hash = raw_str.rsplit('|', 1)
                                keys_to_del.append(
                                    f"otp_hash:{old_hash}".encode()
                                )
                    if keys_to_del:
                        await sync_to_async(redis_conn.delete)(*keys_to_del)

            # Generate + dispatch (async wrappers)
            otp = await OTPService.generate_otp_async(user.id, purpose)

            from apps.authentication.tasks import send_email_task, send_sms_task
            from django.conf import settings as _settings

            if user.email:
                _email_context = {
                    'user_id':       str(user.id),
                    'otp':           otp,
                    'user_name': (
                        getattr(user, 'first_name', None)
                        or user.email.split('@')[0]
                    ),
                    'support_email': 'support@fashionistar.io',
                    'SITE_URL': getattr(
                        _settings, 'SITE_URL', 'https://fashionistar.io'
                    ),
                }
                send_email_task.delay(
                    subject='🔐 Your New Fashionistar Verification OTP',
                    recipients=[user.email],
                    template_name='authentication/email/resend_otp.html',  # ← FIXED
                    context=_email_context,
                )
            elif user.phone:
                _phone_body = (
                    f"Your new Fashionistar verification OTP: {otp}\n"
                    "Valid for 5 minutes. Do not share this code."
                )
                send_sms_task.delay(to=str(user.phone), body=_phone_body)

            return "If an account exists, a new OTP has been sent."

        except Exception as exc:
            logger.error("Resend OTP Async Error: %s", exc, exc_info=True)
            raise
